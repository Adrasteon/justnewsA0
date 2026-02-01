
import os
import sys
from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("fix_schema")

def fix_articles_schema():
    print("Connecting to database...")
    db_service = create_database_service()
    db_service.ensure_conn()
    conn = db_service.mb_conn
    cursor = conn.cursor()

    try:
        print("Checking for 'embedded' column in 'articles' table...")
        cursor.execute("SHOW COLUMNS FROM articles LIKE 'embedded'")
        result = cursor.fetchone()
        
        if result:
            print("Column 'embedded' already exists.")
        else:
            print("Column 'embedded' missing. Adding it...")
            cursor.execute("ALTER TABLE articles ADD COLUMN embedded TINYINT(1) DEFAULT 0")
            conn.commit()
            print("Column 'embedded' added successfully.")
            
    except Exception as e:
        print(f"Error updating schema: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    fix_articles_schema()
