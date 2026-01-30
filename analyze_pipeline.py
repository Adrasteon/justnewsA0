
import sys
import os
sys.path.append(os.getcwd())
from database.utils.migrated_database_utils import create_database_service

def analyze_workflow():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        print("=== Workflow Pipeline Analysis ===")
        
        # 1. Ingested (Total)
        cursor.execute("SELECT COUNT(*) as count FROM articles WHERE is_synthesized = 0")
        ingested = cursor.fetchone()['count']
        print(f"1. Ingested Articles (Raw): {ingested}")
        
        # 2. Analyzed (Sentiment/Metadata)
        # Assuming 'analyzed' flag or sentiment_label presence
        cursor.execute("SELECT COUNT(*) as count FROM articles WHERE is_synthesized = 0 AND analyzed = 1")
        analyzed = cursor.fetchone()['count']
        print(f"2. Analyzed: {analyzed}")
        
        # 3. Fact Checked
        # Check fact_check_status distribution
        cursor.execute("SELECT fact_check_status, COUNT(*) as count FROM articles WHERE is_synthesized = 0 GROUP BY fact_check_status")
        fact_check_stats = cursor.fetchall()
        print("3. Fact Check Status:")
        for row in fact_check_stats:
             status = row['fact_check_status'] if row['fact_check_status'] else "Pending/None"
             print(f"   - {status}: {row['count']}")
             
        # 4. Critic Result (Quality Check)
        cursor.execute("SELECT COUNT(*) as count FROM articles WHERE is_synthesized = 0 AND critic_result IS NOT NULL")
        critiqued = cursor.fetchone()['count']
        print(f"4. Quality Assessed (Critic): {critiqued}")

        # 5. Synthesis (Generated Articles)
        cursor.execute("SELECT COUNT(*) as count FROM articles WHERE is_synthesized = 1")
        synthesized = cursor.fetchone()['count']
        print(f"5. Synthesized Articles: {synthesized}")
        
        if synthesized > 0:
            cursor.execute("SELECT is_published, COUNT(*) as count FROM articles WHERE is_synthesized = 1 GROUP BY is_published")
            pub_stats = cursor.fetchall()
            print("   - Publication Status:")
            for row in pub_stats:
                status = "Published" if row['is_published'] else "Draft"
                print(f"     * {status}: {row['count']}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    analyze_workflow()
