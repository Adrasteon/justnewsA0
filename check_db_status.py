
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

# Setup django or DB connection if needed, or use the project's DB utils
from database.utils.migrated_database_utils import create_database_service

def check_status():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Check total articles
        cursor.execute("SELECT count(*) FROM articles")
        total = cursor.fetchone()[0]
        print(f"Total articles: {total}")
        
        # Check analyzed status
        # I need to guess the column name. 'analyzed', 'status', 'state'?
        # Let's describe the table first
        cursor.execute("DESCRIBE articles")
        columns = [row[0] for row in cursor.fetchall()]
        print(f"Columns: {columns}")
        
        if 'analyzed' in columns:
            cursor.execute("SELECT count(*) FROM articles WHERE analyzed = 1 OR analyzed = TRUE")
            analyzed = cursor.fetchone()[0]
            print(f"Analyzed articles: {analyzed}")
        elif 'status' in columns:
            cursor.execute("SELECT status, count(*) FROM articles GROUP BY status")
            stats = cursor.fetchall()
            print(f"Status distribution: {stats}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_status()
