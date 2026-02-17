
import os
import sys

sys.path.insert(0, os.getcwd())
from database.utils.migrated_database_utils import create_database_service


def check_articles():
    try:
        db_service = create_database_service()
        cursor = db_service.mb_conn.cursor(dictionary=True)

        query = "SELECT COUNT(*) as count, MAX(created_at) as last_insert FROM articles"
        cursor.execute(query)
        result = cursor.fetchone()

        print(f"Total Articles: {result['count']}")
        print(f"Last Insert: {result['last_insert']}")

        cursor.close()
        db_service.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_articles()
