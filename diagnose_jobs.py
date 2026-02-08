
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def diagnose_jobs():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        print("--- Orchestrator Jobs ---")
        cursor.execute("SELECT status, count(*) FROM orchestrator_jobs GROUP BY status")
        print(cursor.fetchall())
        
        print("\n--- Crawler Jobs ---")
        cursor.execute("SELECT status, count(*) FROM crawler_jobs GROUP BY status")
        print(cursor.fetchall())
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    diagnose_jobs()
