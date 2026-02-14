import os
import sys

# Ensure we can import from the project root
sys.path.append(os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
os.environ["FORCE_CPU"] = "1"

from database.utils.migrated_database_utils import create_database_service


def apply_schema_update():
    print("Connecting to database...")
    try:
        db = create_database_service()
        db.ensure_conn()
        print("Connected.")

        conn = db.get_connection()
        cursor = conn.cursor()

        print("Applying Factual Audit schema extensions...")

        # 1. Add 'factual_accuracy_score'
        try:
            print("Adding 'factual_accuracy_score' column using FLOAT...")
            # We use FLOAT or DOUBLE. Python float maps to DOUBLE usually.
            cursor.execute("ALTER TABLE articles ADD COLUMN factual_accuracy_score FLOAT DEFAULT NULL")
            print("Success: Added factual_accuracy_score.")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("Skipped: factual_accuracy_score already exists.")
            else:
                print(f"Error adding factual_accuracy_score: {e}")

        # 2. Add 'fact_check_details'
        try:
            print("Adding 'fact_check_details' column using JSON...")
            cursor.execute("ALTER TABLE articles ADD COLUMN fact_check_details JSON DEFAULT NULL")
            print("Success: Added fact_check_details.")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print("Skipped: fact_check_details already exists.")
            else:
                print(f"Error adding fact_check_details: {e}")

        conn.commit()
        print("Schema update complete.")

    except Exception as e:
        print(f"Fatal Error: {e}")

if __name__ == "__main__":
    apply_schema_update()
