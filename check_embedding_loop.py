import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from database.utils.migrated_database_utils import create_database_service

def check_embedding_status():
    db = create_database_service()
    db.ensure_conn()
    conn = db.mb_conn
    cursor = conn.cursor()

    # 1. Stats
    cursor.execute("SELECT COUNT(*) FROM articles WHERE analyzed=1 AND embedded=1")
    embedded = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM articles WHERE analyzed=1 AND embedded=0")
    pending = cursor.fetchone()[0]
    
    print(f"Embedded: {embedded}")
    print(f"Pending Embedding: {pending}")

    # 2. Check for potential stuck items (oldest pending)
    cursor.execute("""
        SELECT id, created_at FROM articles 
        WHERE analyzed=1 AND embedded=0 
        ORDER BY created_at ASC LIMIT 5
    """)
    stuck = cursor.fetchall()
    if stuck:
        print("Oldest pending items:")
        for row in stuck:
            print(f"  ID: {row[0]}, Created: {row[1]}")

    cursor.close()
    conn.close()

if __name__ == "__main__":
    check_embedding_status()
