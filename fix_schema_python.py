import os
import sys
from database.utils.migrated_database_utils import create_database_service

# Load env vars manually if not loaded (the utils usually do it)
# But let's rely on create_database_service to load from global.env

def fix_schema():
    print("Connecting to DB...")
    db = create_database_service()
    db.ensure_conn()
    print("Connected.")
    
    cursor = db.mb_conn.cursor()
    
    # Check if column exists
    try:
        cursor.execute("SHOW COLUMNS FROM articles LIKE 'embedded'")
        result = cursor.fetchone()
        if result:
            print("Column 'embedded' already exists.")
            return
    except Exception as e:
        print(f"Error checking column: {e}")
        
    print("Adding column 'embedded'...")
    try:
        cursor.execute("ALTER TABLE articles ADD COLUMN embedded BOOLEAN DEFAULT 0")
        print("Column added.")
    except Exception as e:
        print(f"Error adding column: {e}")

    try:
        print("Adding index...")
        cursor.execute("CREATE INDEX idx_articles_embedded ON articles(embedded)")
        print("Index added.")
    except Exception as e:
        print(f"Error adding index (might exist): {e}")

    db.mb_conn.commit()
    cursor.close()
    print("Done.")

if __name__ == "__main__":
    fix_schema()
