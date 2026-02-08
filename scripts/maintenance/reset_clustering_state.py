import os
import sys

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from database.utils.migrated_database_utils import create_database_service
from common.observability import get_logger

logger = get_logger("reset_clustering")

def reset_state():
    print("Initializing database service...")
    db_service = create_database_service()
    db_service.ensure_conn()
    conn = db_service.mb_conn
    cursor = conn.cursor()

    try:
        print("Resetting 'articles' table (clearing clusters, resetting synthesized flag)...")
        # Reset input_cluster_ids to NULL and is_synthesized to 0 for ALL articles
        # This makes them candidates for the new IncrementalClusteringPolicy
        query_articles = """
            UPDATE articles 
            SET input_cluster_ids = NULL, 
                is_synthesized = 0
        """
        cursor.execute(query_articles)
        affected_articles = cursor.rowcount
        print(f"Updated {affected_articles} rows in 'articles'.")

        print("Flushing 'synthesized_articles' table...")
        # Clear out the old "mash-up" stories
        cursor.execute("DELETE FROM synthesized_articles")
        deleted_stories = cursor.rowcount
        print(f"Deleted {deleted_stories} rows from 'synthesized_articles'.")

        print("Flushing 'synthesizer_jobs' table...")
        cursor.execute("DELETE FROM synthesizer_jobs")
        deleted_jobs = cursor.rowcount
        print(f"Deleted {deleted_jobs} rows from 'synthesizer_jobs'.")

        conn.commit()
        print("Committing changes...")
        print("Reset complete. The system is ready for re-clustering and re-synthesis.")

    except Exception as e:
        print(f"Error during reset: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    reset_state()
