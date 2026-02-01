import sys
import os
sys.path.append(os.getcwd())
from database.utils.migrated_database_utils import create_database_service

def check_status():
    db = create_database_service()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    print("--- Crawler Jobs Status ---")
    try:
        cursor.execute("SELECT status, count(*) FROM crawler_jobs GROUP BY status")
        rows = cursor.fetchall()
        for row in rows:
            print(f"{row[0]}: {row[1]}")
    except Exception as e:
        print(f"Error querying crawler_jobs: {e}")

    print("\n--- Articles Count ---")
    try:
        cursor.execute("SELECT count(*) FROM articles")
        count = cursor.fetchone()[0]
        print(f"Total Articles: {count}")
    except Exception as e:
        print(f"Error querying articles: {e}")

if __name__ == "__main__":
    check_status()
