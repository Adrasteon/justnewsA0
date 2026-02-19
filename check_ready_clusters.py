
import os
import sys
import json
from datetime import datetime, timedelta

import mysql.connector
from dotenv import load_dotenv

# Setup paths
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv('global.env')

# DB Config (canonical MariaDB env vars first, then legacy fallback)
DB_HOST = os.getenv("MARIADB_HOST") or os.getenv("DB_HOST", "mariadb")
DB_PORT = int(os.getenv("MARIADB_PORT") or os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("MARIADB_USER") or os.getenv("DB_USER", "justnews")
DB_PASSWORD = os.getenv("MARIADB_PASSWORD") or os.getenv("DB_PASSWORD", "dev_justnews_password")
DB_NAME = os.getenv("MARIADB_DB") or os.getenv("DB_NAME", "justnews")

def check_ready():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cursor = conn.cursor()
        
        query = """
            SELECT input_cluster_ids, created_at FROM articles 
            WHERE is_synthesized = 0 
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
        cluster_titles = {} # Optional, if we wanted to fetch titles

        print(f"Scanned {len(rows)} unsynthesized articles.")

        for row in rows:
            try:
                c_ids = json.loads(row[0])
                created_at = row[1]
                
                if isinstance(c_ids, list) and c_ids:
                    cid = c_ids[0]
                    counts[cid] = counts.get(cid, 0) + 1
                    
                    if created_at:
                        current_max = latest_activity.get(cid)
                        if not current_max or created_at > current_max:
                            latest_activity[cid] = created_at
            except Exception as e:
                continue
        
        now = datetime.now()
        maturity_window = timedelta(minutes=20)
        
        ready_clusters = 0
        waiting_clusters = 0
        
        print(f"\nCluster Status (Snapshot):")
        print(f"{'Cluster ID':<15} | {'Count':<5} | {'Latest Article':<20} | {'Age (Mins)':<10} | {'Status'}")
        print("-" * 75)
        
        for cid, count in counts.items():
            last_ts = latest_activity.get(cid)
            if not last_ts:
                continue
                
            age = now - last_ts
            age_mins = age.total_seconds() / 60
            
            status = "WAITING"
            if age > maturity_window:
                status = "READY"
                if count >= 2:
                    ready_clusters += 1
            else:
                waiting_clusters += 1
                
            print(f"{cid[:12]:<15} | {count:<5} | {last_ts.strftime('%H:%M:%S')}            | {age_mins:.1f}       | {status}")

        print("\nSummary:")
        print(f"Ready for Synthesis (Count >= 2 + Age > 20m): {ready_clusters}")
        print(f"Waiting for Maturity (Age < 20m): {waiting_clusters}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    check_ready()
