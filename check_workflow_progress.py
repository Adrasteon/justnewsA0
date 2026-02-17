import os
import mysql.connector
import time
from dotenv import load_dotenv

load_dotenv("/app/global.env")

def get_db_conn():
    host = os.getenv("MARIADB_HOST", "mariadb")
    port = int(os.getenv("MARIADB_PORT", 3306))
    user = os.getenv("MARIADB_USER", "justnews")
    password = os.getenv("MARIADB_PASSWORD", "dev_justnews_password")
    database = os.getenv("MARIADB_DB", "justnews")
    
    return mysql.connector.connect(
        host=host, port=port, user=user, password=password, database=database
    )

def check_progress():
    conn = get_db_conn()
    cursor = conn.cursor(dictionary=True)
    
    # Check total articles
    cursor.execute("SELECT COUNT(*) as count FROM articles")
    total = cursor.fetchone()['count']
    
    # Check analyzed
    cursor.execute("SELECT COUNT(*) as count FROM articles WHERE analyzed = 1")
    analyzed = cursor.fetchone()['count']
    
    # Check embedded/memory status
    # Note: Column might be 'embedded' or we check vector store. 
    # Let's check 'embedded' column first if it exists.
    try:
        cursor.execute("SELECT COUNT(*) as count FROM articles WHERE embedded = 1")
        embedded = cursor.fetchone()['count']
    except Exception:
        embedded = "Column 'embedded' not found/used"

    # Check for recent articles (last 100) and their specific status
    cursor.execute("""
        SELECT id, created_at, analyzed, embedded 
        FROM articles 
        ORDER BY created_at DESC 
        LIMIT 20
    """)
    recent = cursor.fetchall()
    
    print(f"Total Articles: {total}")
    print(f"Analyzed: {analyzed}")
    print(f"Embedded: {embedded}")
    print("\nRecent 20 Articles Status:")
    print(f"{'ID':<6} | {'Created At':<20} | {'Analyzed':<8} | {'Embedded':<8}")
    print("-" * 50)
    for r in recent:
        emb_status = r.get('embedded', 'N/A')
        print(f"{r['id']:<6} | {str(r['created_at']):<20} | {r['analyzed']:<8} | {emb_status:<8}")
        
    conn.close()

if __name__ == "__main__":
    check_progress()
