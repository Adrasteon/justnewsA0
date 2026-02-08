
import os
import sys
import json
import ast

# Add project root to path
sys.path.append(os.getcwd())

from database.utils.migrated_database_utils import create_database_service

def check_progress():
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        print("--- Cluster Analysis ---")
        
        # 1. Get all cluster IDs from articles
        cursor.execute("SELECT id, input_cluster_ids FROM articles WHERE input_cluster_ids IS NOT NULL AND input_cluster_ids != '' AND input_cluster_ids != '[]'")
        rows = cursor.fetchall()
        
        all_clusters = set()
        article_to_cluster_map = {}
        
        for row in rows:
            article_id = row[0]
            cluster_data = row[1]
            try:
                # Try parsing as JSON first
                clusters = json.loads(cluster_data)
            except:
                try:
                    # Try parsing as python list string
                    clusters = ast.literal_eval(cluster_data)
                except:
                    print(f"Warning: Could not parse cluster data for article {article_id}: {cluster_data}")
                    continue
            
            if isinstance(clusters, list):
                for c in clusters:
                    all_clusters.add(c)
                    if c not in article_to_cluster_map:
                        article_to_cluster_map[c] = []
                    article_to_cluster_map[c].append(article_id)
            elif isinstance(clusters, str):
                 all_clusters.add(clusters)
                 if clusters not in article_to_cluster_map:
                        article_to_cluster_map[clusters] = []
                 article_to_cluster_map[clusters].append(article_id)

        total_clusters = len(all_clusters)
        print(f"Total Unique Clusters Found: {total_clusters}")
        
        # 2. Get completed clusters
        cursor.execute("SELECT cluster_id FROM synthesized_articles")
        completed_rows = cursor.fetchall()
        completed_clusters = set(row[0] for row in completed_rows)
        
        print(f"Completed Clusters (Synthesized): {len(completed_clusters)}")
        
        # 3. Calculate remaining
        remaining_clusters = all_clusters - completed_clusters
        print(f"Remaining Clusters: {len(remaining_clusters)}")
        
        # 4. Analyze remaining cluster sizes
        remaining_sizes = [len(article_to_cluster_map[c]) for c in remaining_clusters]
        if remaining_sizes:
            avg_size = sum(remaining_sizes) / len(remaining_sizes)
            max_size = max(remaining_sizes)
            min_size = min(remaining_sizes)
            print(f"Remaining Cluster Stats: Avg Size={avg_size:.2f}, Max={max_size}, Min={min_size}")
        else:
            print("No remaining clusters!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_progress()
