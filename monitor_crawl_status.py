import os
import time
import mysql.connector
from datetime import datetime

config = {
    'user': 'justnews',
    'password': 'dev_justnews_password',
    'host': 'mariadb',
    'database': 'justnews',
    'raise_on_warnings': True
}

def monitor():
    try:
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor(dictionary=True)
        
        # Check if tables exist
        cursor.execute("SHOW TABLES LIKE 'crawler_jobs'")
        has_jobs = cursor.fetchone()
        
        while True:
            print(f"\n=== CRAWL MONITORING {datetime.now().strftime('%H:%M:%S')} ===")
            
            if has_jobs:
                cursor.execute("SELECT status, COUNT(*) as count FROM crawler_jobs GROUP BY status")
                jobs = cursor.fetchall()
                print("\n[Crawler Jobs]")
                if jobs:
                    for j in jobs:
                        print(f"  {j['status']}: {j['count']}")
                else:
                    print("  No jobs found.")
            
            # Articles
            cursor.execute("SELECT COUNT(*) as total FROM articles")
            total_articles = cursor.fetchone()['total']
            
            cursor.execute("SELECT COUNT(*) as analyzed FROM articles WHERE analyzed=1")
            analyzed = cursor.fetchone()['analyzed']
            
            cursor.execute("SELECT COUNT(*) as embedded FROM articles WHERE embedded=1")
            embedded = cursor.fetchone()['embedded']
            
            # Recent Articles
            print("\n[Articles Pipeline]")
            print(f"  Total Ingested: {total_articles}")
            print(f"  Analyzed:       {analyzed}")
            print(f"  Embedded:       {embedded}")

            # Clusters (if table exists)
            try:
                cursor.execute("SELECT COUNT(*) as count FROM clusters")
                clusters = cursor.fetchone()['count']
                print(f"  Clusters:       {clusters}")
            except:
                pass

            # Synthesis
            try:
                cursor.execute("SELECT status, COUNT(*) as count FROM synthesized_articles GROUP BY status")
                synth = cursor.fetchall()
                print("\n[Synthesis]")
                if synth:
                    for s in synth:
                        print(f"  {s['status']}: {s['count']}")
                else:
                    print("  No synthesized articles.")
            except:
                pass

            time.sleep(5)
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals() and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    monitor()
