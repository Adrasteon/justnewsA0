#!/usr/bin/env python
"""
Phase 1 Live Crawl Test - Full deployment validation.

Crawls all 540 news sources with:
- Max 5 articles per site
- Concurrency: 3
- Real-time ingestion and metrics tracking
"""

import os
import sys
import time
import json
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = ""

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("phase1_crawl")

# Configuration
CRAWL_SERVICE_URL = "http://localhost:8015"
MAX_ARTICLES_PER_SITE = 5
CONCURRENT_SITES = 3
BATCH_SIZE = 20  # Sites per batch request


def get_all_sources() -> list:
    """Fetch all sources from database."""
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, domain, name, url, country,
                   JSON_EXTRACT(metadata, '$.crawl_profile') as profile
            FROM sources 
            ORDER BY country, name
        """)
        sources = cursor.fetchall()
        cursor.close()
        db_service.close()
        
        return sources
    except Exception as e:
        logger.error(f"Failed to fetch sources: {e}")
        sys.exit(1)


def split_into_batches(items: list, batch_size: int) -> list:
    """Split items into batches of specified size."""
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def submit_crawl_batch(domains: list, batch_num: int, total_batches: int) -> dict:
    """
    Submit a batch of domains for crawling to the unified crawl service.
    
    Returns: {status: 'success'|'error', job_id: str, error: str}
    """
    try:
        payload = {
            "name": "unified_production_crawl",
            "args": [],
            "kwargs": {
                "domains": domains,
                "max_articles_per_site": MAX_ARTICLES_PER_SITE,
                "concurrent_sites": CONCURRENT_SITES
            }
        }
        
        print(f"  [Batch {batch_num}/{total_batches}] Submitting {len(domains)} domains...", end=" ")
        
        response = requests.post(
            f"{CRAWL_SERVICE_URL}/unified_production_crawl",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 202:
            result = response.json()
            job_id = result.get('job_id', 'unknown')
            print(f"✓ Job {job_id}")
            return {
                'status': 'success',
                'job_id': job_id,
                'domains': len(domains),
                'batch_num': batch_num
            }
        else:
            print(f"✗ HTTP {response.status_code}")
            return {
                'status': 'error',
                'error': f"HTTP {response.status_code}: {response.text[:200]}",
                'batch_num': batch_num
            }
            
    except requests.ConnectionError:
        print(f"✗ Connection failed")
        return {
            'status': 'error',
            'error': 'Connection refused (service not running?)',
            'batch_num': batch_num
        }
    except Exception as e:
        print(f"✗ Error")
        return {
            'status': 'error',
            'error': str(e)[:200],
            'batch_num': batch_num
        }


def check_job_status(job_id: str) -> dict:
    """Check status of a submitted crawl job."""
    try:
        response = requests.get(
            f"{CRAWL_SERVICE_URL}/job/{job_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return {'status': 'unknown', 'error': f"HTTP {response.status_code}"}
            
    except Exception as e:
        return {'status': 'unknown', 'error': str(e)}


def run_phase1_crawl():
    """Execute Phase 1 live crawl test."""
    
    print("\n" + "=" * 80)
    print("🚀 PHASE 1 LIVE CRAWL TEST")
    print("=" * 80)
    print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Step 1: Fetch all sources
    print("📋 STEP 1: Loading sources from database...")
    sources = get_all_sources()
    total_sources = len(sources)
    domains = [s['domain'] for s in sources]
    
    print(f"   ✓ Loaded {total_sources} sources")
    print(f"   • Top source: {sources[0]['name']} ({sources[0]['country']})")
    print(f"   • Region spread: {len(set(s['country'] for s in sources))} countries\n")
    
    # Step 2: Prepare batches
    print("📊 STEP 2: Preparing crawl batches...")
    batches = split_into_batches(domains, BATCH_SIZE)
    print(f"   ✓ Created {len(batches)} batches ({BATCH_SIZE} domains/batch)\n")
    
    # Step 3: Submit batches
    print("🔄 STEP 3: Submitting crawl jobs...")
    print("-" * 80)
    
    jobs = []
    for batch_num, batch in enumerate(batches, 1):
        result = submit_crawl_batch(batch, batch_num, len(batches))
        jobs.append(result)
        time.sleep(0.5)  # Small delay between submissions
    
    successful_batches = sum(1 for j in jobs if j['status'] == 'success')
    failed_batches = sum(1 for j in jobs if j['status'] == 'error')
    
    print("-" * 80)
    print(f"   ✓ Submitted {successful_batches} batches successfully")
    
    if failed_batches > 0:
        print(f"   ⚠️  {failed_batches} batches failed:")
        for job in jobs:
            if job['status'] == 'error':
                print(f"      - Batch {job['batch_num']}: {job['error']}")
        print()
    
    # Step 4: Display job summary
    print("\n📈 STEP 4: Job summary")
    print("-" * 80)
    
    job_ids = [j.get('job_id') for j in jobs if j['status'] == 'success']
    total_domains = sum(j.get('domains', 0) for j in jobs if j['status'] == 'success')
    
    print(f"   Total domains submitted: {total_domains}/{total_sources}")
    print(f"   Job IDs: {', '.join(job_ids[:3])}" + 
          (f" ... ({len(job_ids) - 3} more)" if len(job_ids) > 3 else ""))
    
    # Step 5: Configuration display
    print("\n⚙️  STEP 5: Crawl configuration")
    print("-" * 80)
    print(f"   • Max articles per site: {MAX_ARTICLES_PER_SITE}")
    print(f"   • Concurrent sites: {CONCURRENT_SITES}")
    print(f"   • Total batch size: {total_domains} domains")
    print(f"   • Estimated articles: {total_domains * MAX_ARTICLES_PER_SITE} (max)")
    
    # Step 6: Monitoring instructions
    print("\n📋 STEP 6: Monitoring")
    print("-" * 80)
    print(f"""
   Monitor crawl progress with:
   $ for job in {job_ids[0] if job_ids else 'JOB_ID'}; do
       curl -s http://localhost:8015/job/$job | jq .
     done
   
   Check database ingestion:
   $ python << 'EOF'
from database.utils.migrated_database_utils import create_database_service
db = create_database_service()
cursor = db.mb_conn.cursor(dictionary=True)
cursor.execute("SELECT COUNT(*) as count FROM articles")
print(f"Total articles in DB: {{cursor.fetchone()['count']}}")
EOF
  
   Current time: {datetime.now().strftime('%H:%M:%S')}
   Estimated completion: {(datetime.fromtimestamp(time.time() + total_domains * 5 / CONCURRENT_SITES / 60)).strftime('%H:%M:%S')} (rough estimate)
""")
    
    # Log submission
    logger.info(f"Phase 1 crawl started: {total_sources} sources, {len(batches)} batches, {job_ids[0] if job_ids else 'N/A'} lead job")
    
    print("\n" + "=" * 80)
    print(f"✅ Crawl submission complete. Monitoring jobs: {successful_batches}/{len(batches)}")
    print("=" * 80 + "\n")
    
    return {
        'timestamp': datetime.now().isoformat(),
        'total_sources': total_sources,
        'batches': len(batches),
        'successful_batches': successful_batches,
        'failed_batches': failed_batches,
        'job_ids': job_ids,
        'config': {
            'max_articles_per_site': MAX_ARTICLES_PER_SITE,
            'concurrent_sites': CONCURRENT_SITES,
            'batch_size': BATCH_SIZE
        }
    }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Phase 1 live crawl test')
    parser.add_argument('--check-only', action='store_true', help='Only fetch sources, don\'t crawl')
    args = parser.parse_args()
    
    if args.check_only:
        print("Checking sources...")
        sources = get_all_sources()
        print(f"✓ {len(sources)} sources available")
        sys.exit(0)
    
    # Run the crawl
    result = run_phase1_crawl()
    
    # Save result for later reference
    with open('/tmp/phase1_crawl_result.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"📝 Results saved to /tmp/phase1_crawl_result.json")
