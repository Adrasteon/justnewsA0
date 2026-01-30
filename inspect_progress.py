
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def inspect_progress():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        print("--- Detailed Progress Inspection ---")
        
        # 1. Summarization Progress
        cursor.execute("SELECT count(*) FROM articles WHERE summary IS NOT NULL AND summary != ''")
        summary_count = cursor.fetchone()[0]
        print(f"Summarized Articles: {summary_count}")
        
        # 2. Fact Check Progress
        cursor.execute("SELECT count(*) FROM articles WHERE fact_check_status IS NOT NULL")
        fc_count = cursor.fetchone()[0]
        print(f"Fact Checked Articles: {fc_count}")
        
        # 3. Clustering Progress (Column based)
        cursor.execute("SELECT count(*) FROM articles WHERE input_cluster_ids IS NOT NULL AND input_cluster_ids != '[]' AND input_cluster_ids != ''")
        clustered_count = cursor.fetchone()[0]
        print(f"Clustered Articles (Ready for Synthesis): {clustered_count}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_progress()
