
import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def check_clustering_ready():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Check environment variable for CLUSTER_DATERANGE
        try:
            days_range = int(os.environ.get("CLUSTER_DATERANGE", 7))
        except ValueError:
            days_range = 7
        cutoff_date = datetime.now() - timedelta(days=days_range)
        print(f"Checking for articles eligible for clustering (Last {days_range} days, since {cutoff_date})")

        query = """
            SELECT count(*) FROM articles 
            WHERE fact_check_status IS NOT NULL 
              AND fact_check_status != ''
              AND (input_cluster_ids IS NULL OR input_cluster_ids = '[]' OR input_cluster_ids = '')
              AND created_at >= %s
        """
        cursor.execute(query, (cutoff_date,))
        ready_count = cursor.fetchone()[0]
        print(f"Articles ready for clustering: {ready_count}")
        
        # Also check how many have cluster IDs but aren't synthesized
        query_clustered = """
            SELECT count(*) FROM articles
            WHERE input_cluster_ids IS NOT NULL 
              AND input_cluster_ids != '[]' 
              AND input_cluster_ids != ''
              AND (is_synthesized = 0 OR is_synthesized IS NULL)
        """
        cursor.execute(query_clustered)
        clustered_not_synthesized = cursor.fetchone()[0]
        print(f"Articles clustered but not synthesized: {clustered_not_synthesized}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_clustering_ready()
