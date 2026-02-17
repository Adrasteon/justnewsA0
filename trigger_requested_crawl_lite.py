import os
import sys
import requests
import time
import mysql.connector
from dotenv import load_dotenv

# Load environment
load_dotenv('/app/global.env')

def trigger_crawl():
    print("=== Requesting Crawl of All Sources (Lite) ===")
    
    # 1. Fetch domains from database using raw connector
    try:
        conn = mysql.connector.connect(
            host=os.getenv('MARIADB_HOST'),
            user=os.getenv('MARIADB_USER'),
            password=os.getenv('MARIADB_PASSWORD'),
            database=os.getenv('MARIADB_DB')
        )
        cursor = conn.cursor()

        cursor.execute("SELECT domain FROM sources")
        domains = [r[0] for r in cursor.fetchall()]
        print(f"Found {len(domains)} domains.")
        conn.close()
        
        if not domains:
            print("No sources found in database.")
            return

        # 2. Configure Payload
        payload = {
            "name": "unified_production_crawl",
            "args": [],
            "kwargs": {
                "domains": domains,
                "max_articles_per_site": 3,
                "concurrent_sites": 3
            }
        }

        # 3. Send Request to Crawler Agent (Port 8022)
        url = "http://localhost:8022/unified_production_crawl"
        print(f"Sending request to {url}...")
        
        max_retries = 3
        for i in range(max_retries):
            try:
                # Increased timeout to 60 seconds
                resp = requests.post(url, json=payload, timeout=60)
                if resp.status_code == 202:
                    job_id = resp.json().get('job_id')
                    print(f"✅ Success! Crawl job initiated.")
                    print(f"🆔 Job ID: {job_id}")
                    return
                else:
                    print(f"❌ Failed: {resp.status_code} - {resp.text}")
                    return
            except requests.exceptions.ReadTimeout:
                print(f"Read timeout from crawler agent at {url}, retrying... ({i+1}/{max_retries})")
                time.sleep(3)
            except requests.exceptions.ConnectionError:
                if i < max_retries - 1:
                    print(f"Crawler agent at {url} not ready, retrying... ({i+1}/{max_retries})")
                    time.sleep(3)
                else:
                    print(f"❌ Could not connect to crawler agent at {url}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    trigger_crawl()
