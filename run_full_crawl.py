import os
import sys

import requests

sys.path.append(os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
# Only disable CUDA devices when explicitly requested (DEV_CPU_ONLY=1)
if os.environ.get("DEV_CPU_ONLY", "") == "1" or os.environ.get("FORCE_CPU", "") == "1":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

from database.utils.migrated_database_utils import create_database_service


def run_crawl():
    print("Fetching active domains...")
    try:
        db = create_database_service()
        db.ensure_conn()
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT domain FROM sources")
        domains = [r[0] for r in cursor.fetchall()]
        print(f"Found {len(domains)} domains.")

        # Prepare the call
        # Endpoint: POST /unified_production_crawl
        # Body: ToolCall -> { "name": "unified_production_crawl", "kwargs": { ... } }

        payload = {
            "name": "unified_production_crawl",
            "args": [],
            "kwargs": {
                "domains": domains,
                "max_articles_per_site": 10,
                "concurrent_sites": 3
            }
        }

        print("Sending crawl request...")
        resp = requests.post(
            "http://localhost:8015/unified_production_crawl",
            json=payload,
            timeout=10
        )

        if resp.status_code == 202:
            print(f"Success! Job ID: {resp.json().get('job_id')}")
        else:
            print(f"Failed: {resp.status_code} - {resp.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_crawl()
