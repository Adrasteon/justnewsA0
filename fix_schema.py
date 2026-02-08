import os
import sys

# Ensure we can import from the project root
sys.path.append(os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
os.environ["FORCE_CPU"] = "1"

from database.utils.migrated_database_utils import create_database_service


def fix_schema():
    print("Connecting to database...")
    try:
        db = create_database_service()
        db.ensure_conn()
        print("Connected.")

        conn = db.get_connection()
        cursor = conn.cursor()

        print("Applying schema fixes...")

        # 1. Add 'analyzed' column to articles
        try:
            print("Adding 'analyzed' column to articles...")
            cursor.execute("ALTER TABLE articles ADD COLUMN analyzed TINYINT(1) DEFAULT 0")
            print("Success.")
        except Exception as e:
            print(f"Skipping analyzed: {e}")

        # 2. Add 'source_id' column to articles
        try:
            print("Adding 'source_id' column to articles...")
            cursor.execute("ALTER TABLE articles ADD COLUMN source_id INT")
            print("Success.")
        except Exception as e:
            print(f"Skipping source_id: {e}")

        # 3. Modify 'result' column in crawler_jobs to LONGTEXT
        try:
            print("Modifying 'result' column in crawler_jobs...")
            cursor.execute("ALTER TABLE crawler_jobs MODIFY result LONGTEXT")
            print("Success.")
        except Exception as e:
             print(f"Skipping crawler_jobs modification: {e}")


    except Exception as e:
        print(f"Fatal Error: {e}")

if __name__ == "__main__":
    fix_schema()
