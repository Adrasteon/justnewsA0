import os
import sys

# Ensure we can import from the project root
sys.path.append(os.getcwd())
# Use the correct env settings
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
os.environ["FORCE_CPU"] = "1"

from database.utils.migrated_database_utils import create_database_service


def inspect_all_tables():
    print("Connecting to database...")
    try:
        db = create_database_service()
        db.ensure_conn()
        print("Connected.")

        conn = db.get_connection()
        cursor = conn.cursor()

        print("Showing tables:")
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()

        for table in tables:
            table_name = table[0]
            print(f"\nTABLE: {table_name}")
            print("-" * 30)
            cursor.execute(f"DESCRIBE {table_name}")
            columns = cursor.fetchall()
            for col in columns:
                 print(col)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_all_tables()
