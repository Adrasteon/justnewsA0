
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
        
        print("--- Raw Articles Diagnostics ---")
        
        # 1. Check Fact Check Status for Raw Articles
        cursor.execute("""
            SELECT fact_check_status, count(*) 
            FROM articles 
            WHERE is_synthesized = 0 OR is_synthesized IS NULL 
            GROUP BY fact_check_status
        """)
        results = cursor.fetchall()
        print(f"Raw Articles Fact Check Status Distribution: {results}")

        # 2. Check Analyzed for Raw Articles
        cursor.execute("""
            SELECT analyzed, count(*) 
            FROM articles 
            WHERE is_synthesized = 0 OR is_synthesized IS NULL 
            GROUP BY analyzed
        """)
        results = cursor.fetchall()
        print(f"Raw Articles Analyzed Status (0=Wait, 1=Done): {results}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnose()
