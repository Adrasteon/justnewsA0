
import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from database.utils.migrated_database_utils import create_database_service

def check_ready():
    try:
        db_service = create_database_service()
        db_service.ensure_conn()
        cursor = db_service.mb_conn.cursor()
        
        query = """
            SELECT input_cluster_ids, created_at, is_synthesized FROM articles 
            WHERE (input_cluster_ids LIKE '%CL-fc5c8e0c%' OR is_synthesized = 0)
              AND input_cluster_ids IS NOT NULL 
              AND input_cluster_ids != '[]'
              AND input_cluster_ids != ''
            ORDER BY created_at ASC
            LIMIT 1000
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        counts = {}
        latest_activity = {}
        
        print(f"Scanned {len(rows)} articles (mixed query).")

        for row in rows:
            try:
                c_ids = json.loads(row[0])
                created_at = row[1]
                is_syn = row[2]
                
                if isinstance(c_ids, list) and c_ids:
                    cid = c_ids[0]
                    # Only count strictly for the big cluster to see debug info, or all if un-syn
                    if 'CL-fc5c8e0c' in cid:
                        print(f"DEBUG: Found target cluster item {cid} Syn: {is_syn} Time: {created_at}")

                    if is_syn == 0:
                        counts[cid] = counts.get(cid, 0) + 1
                        
                        if created_at:
                            current_max = latest_activity.get(cid)
                            if not current_max or created_at > current_max:
                                latest_activity[cid] = created_at
            except Exception as e:
                continue
        
        # Determine strict or naive datetime
        now = datetime.now()
        maturity_window = timedelta(minutes=20)
        
        ready_clusters = 0
        waiting_clusters = 0
        
        print(f"\nCluster Status (Snapshot):")
        print(f"{'Cluster ID':<15} | {'Count':<5} | {'Latest Article':<20} | {'Age (Mins)':<10} | {'Status'}")
        print("-" * 80)
        
        count_display = 0
        for cid, count in counts.items():
            last_ts = latest_activity.get(cid)
            if not last_ts:
                continue
                
            # Handle possible timezone awareness mismatch
            # If last_ts is naive, use now() naive. If aware, simple substraction might fail if now is naive.
            # Assuming naive for now as standard MySQL behavior.
            
            try:
                age = now - last_ts
            except TypeError:
                # If one is aware and other isn't, fallback
                age = now - last_ts.replace(tzinfo=None)

            age_mins = age.total_seconds() / 60
            
            status = "WAITING"
            if age > maturity_window:
                status = "READY"
                if count >= 2:
                    ready_clusters += 1
            else:
                waiting_clusters += 1
            
            if count_display < 20: # Only list top 20
                print(f"{cid[:12]:<15} | {count:<5} | {str(last_ts):<20} | {age_mins:.1f}       | {status}")
                count_display += 1

        print(f"... (and more) ...")
        print("\nSummary:")
        print(f"Total Clusters Found in batch: {len(counts)}")
        print(f"Ready for Synthesis (Count >= 2 + Age > 20m): {ready_clusters}")
        print(f"Waiting for Maturity (Age < 20m): {waiting_clusters}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_ready()
