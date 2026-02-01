import os
import sys
import json
from collections import Counter

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from database.utils.migrated_database_utils import create_database_service
from common.observability import get_logger

def check_clustering_status():
    db_service = create_database_service()
    db_service.ensure_conn()
    cursor = db_service.mb_conn.cursor()

    # 1. Total clustered articles
    cursor.execute("SELECT COUNT(*) FROM articles WHERE input_cluster_ids IS NOT NULL AND input_cluster_ids != '[]'")
    clustered_count = cursor.fetchone()[0]

    # 2. Total articles waiting
    cursor.execute("SELECT COUNT(*) FROM articles WHERE fact_check_status IS NOT NULL AND (input_cluster_ids IS NULL OR input_cluster_ids = '[]')")
    waiting_count = cursor.fetchone()[0]

    # 3. Cluster Sizes
    cursor.execute("SELECT input_cluster_ids FROM articles WHERE input_cluster_ids IS NOT NULL")
    rows = cursor.fetchall()
    
    cluster_counts = Counter()
    for row in rows:
        try:
            cids = json.loads(row[0])
            if cids:
                cluster_counts[cids[0]] += 1
        except:
            pass

    print(f"--- Clustering Status ---")
    print(f"Articles Clustered: {clustered_count}")
    print(f"Articles Pending:   {waiting_count}")
    print(f"Total Clusters:     {len(cluster_counts)}")
    
    if len(cluster_counts) > 0:
        common = cluster_counts.most_common(10)
        print("\nTop 10 Clusters by Size:")
        for cid, count in common:
            print(f"  {cid}: {count} articles")
    
        singles = sum(1 for c in cluster_counts.values() if c == 1)
        print(f"\nSingleton Clusters: {singles}")
        print(f"Multi-Article Clusters: {len(cluster_counts) - singles}")

    cursor.close()
    db_service.mb_conn.close()

if __name__ == "__main__":
    check_clustering_status()
