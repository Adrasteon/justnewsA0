
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def diagnose():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        print("--- Database Tables ---")
        cursor.execute("SHOW TABLES")
        tables = [t[0] for t in cursor.fetchall()]
        print(tables)
        
        print("\n--- Articles Workflow Status ---")
        
        # 1. Total Raw Articles
        cursor.execute("SELECT count(*) FROM articles WHERE is_synthesized = 0 OR is_synthesized IS NULL")
        raw_count = cursor.fetchone()[0]
        print(f"Raw Articles (Ingested): {raw_count}")
        
        # 2. Raw Analysis Status
        cursor.execute("""
            SELECT analyzed, count(*) 
            FROM articles 
            WHERE is_synthesized = 0 OR is_synthesized IS NULL 
            GROUP BY analyzed
        """)
        analysis_stats = cursor.fetchall()
        print(f"Raw Articles Analysis Status (0=Pending, 1=Done): {analysis_stats}")

        # 3. Clustering Status (Check if clusters table exists)
        if 'clusters' in tables:
            cursor.execute("SELECT count(*) FROM clusters")
            clusters_count = cursor.fetchone()[0]
            print(f"Clusters Formed: {clusters_count}")
            
            cursor.execute("SELECT status, count(*) FROM clusters GROUP BY status")
            cluster_stats = cursor.fetchall()
            print(f"Cluster Status Breakdown: {cluster_stats}")
        else:
            print("No 'clusters' table found.")

        # 4. Synthesized Articles
        cursor.execute("SELECT count(*) FROM articles WHERE is_synthesized = 1")
        synth_count = cursor.fetchone()[0]
        print(f"Synthesized Articles (Generated): {synth_count}")
        
        if synth_count > 0:
            # 5. Fact Check Status for Synthesized
            cursor.execute("""
                SELECT fact_check_status, count(*) 
                FROM articles 
                WHERE is_synthesized = 1 
                GROUP BY fact_check_status
            """)
            fc_stats = cursor.fetchall()
            print(f"Synthesized Articles Fact Check Status: {fc_stats}")
            
            # 6. Publication Status
            cursor.execute("""
                SELECT is_published, count(*) 
                FROM articles 
                WHERE is_synthesized = 1 
                GROUP BY is_published
            """)
            pub_stats = cursor.fetchall()
            print(f"Synthesized Articles Publication Status: {pub_stats}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    diagnose()
