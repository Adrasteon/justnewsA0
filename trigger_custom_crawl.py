import os
import sys
import requests

sys.path.append(os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
# Don't disable GPUs unless explicitly requested for dev-only runs
if os.environ.get("DEV_CPU_ONLY", "") == "1" or os.environ.get("FORCE_CPU", "") == "1":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""

from database.utils.migrated_database_utils import create_database_service

def run_custom_crawl():
    print("=== Starting Custom Crawl Request ===")
    
    # 1. Fetch domains
    print("Fetching active domains from database...")
    try:
        db = create_database_service()
        conn = db.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT domain FROM sources")
        domains = [r[0] for r in cursor.fetchall()]
        print(f"Found {len(domains)} domains.")
        
        if not domains:
            print("No sources found in database! Aborting.")
            return

        # 2. Configure Crawl
        MAX_ARTICLES = 20
        CONCURRENCY = 3
        
        print(f"Configuring crawl: {MAX_ARTICLES} articles/site, {CONCURRENCY} concurrent sites")

        payload = {
            "name": "unified_production_crawl",
            "args": [],
            "kwargs": {
                "domains": domains,
                "max_articles_per_site": MAX_ARTICLES,
                "concurrent_sites": CONCURRENCY,
                # Force generic/ai_enhanced by profile or let auto-detect?
                # The user previously deprecated ultra_fast.
                # The crawler engine should respect that via the changes we made to _determine_optimal_strategy
            }
        }

        # 3. Send Request
        cralwer_port = os.environ.get("CRAWLER_AGENT_PORT", "8015")
        url = f"http://localhost:{cralwer_port}/unified_production_crawl"
        
        print(f"Sending request to {url}...")
        resp = requests.post(
            url,
            json=payload,
            timeout=10
        )

        if resp.status_code == 202:
            data = resp.json()
            job_id = data.get('job_id')
            print(f"✅ Success! Crawl job initiated.")
            print(f"🆔 Job ID: {job_id}")
            print(f"To monitor logs: tail -f logs/crawler.log")
        else:
            print(f"❌ Failed to initiate crawl: {resp.status_code}")
            print(f"Response: {resp.text}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_custom_crawl()
