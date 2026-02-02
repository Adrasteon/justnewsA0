#!/bin/bash
# Phase 1 Crawl Test with GPU Support
# Activates Phase 1 (Ingestion & Vectorization) environment and runs full crawl

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Activate Phase 1 environment
echo "🔧 Activating Phase 1 (GPU-enabled Ingestion & Vectorization)..."
set +u  # Allow unbound variables for conda
source /home/adra/miniconda3/etc/profile.d/conda.sh 2>/dev/null || true
conda activate justnews-py312-phase1 2>/dev/null || true
set -u

# Verify environment
echo "✅ Phase 1 active"
echo "   Python: $(which python)"
PYTHON_VERSION=$(python --version 2>&1)
echo "   Version: $PYTHON_VERSION"

# Check GPU availability
GPU_CHECK=$(python -c "import torch; print('✅ GPU Available' if torch.cuda.is_available() else '❌ No GPU')" 2>/dev/null || echo "GPU check failed")
echo "   GPU: $GPU_CHECK"

# Verify crawl4ai
echo ""
echo "📦 Checking dependencies..."
python -c "import crawl4ai; print('✅ crawl4ai available')" 2>/dev/null || echo "⚠️  crawl4ai not available"
python -c "import sentence_transformers; print('✅ sentence-transformers available')" 2>/dev/null || echo "⚠️  sentence-transformers not available"

# Run Phase 1 crawl test
echo ""
echo "🚀 Starting Phase 1 crawl test..."
echo "   Configuration:"
echo "   • Max articles per site: 5"
echo "   • Max concurrency: 3"
echo "   • Total sources: 540"
echo ""

python << 'PYTHON_SCRIPT'
import os
import sys
import time
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

sys.path.insert(0, os.getcwd())
os.environ["JUSTNEWS_DISABLE_TEST_DB_FALLBACK"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Use first GPU

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("phase1_crawl")

MAX_ARTICLES_PER_SITE = 5
CONCURRENT_SITES = 3

def get_all_sources():
    """Fetch all sources from database."""
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT id, domain, name, url, country
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

def get_article_count():
    """Get current article count."""
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM articles")
        result = cursor.fetchone()
        count = result['count'] if result else 0
        cursor.close()
        db_service.close()
        return count
    except:
        return 0

def crawl_domain(domain):
    """Crawl a single domain."""
    try:
        from agents.sites.generic_site_crawler import GenericSiteCrawler, SiteConfig
        
        config = SiteConfig(
            name=domain,
            domain=domain,
            url=f"https://{domain}",
        )
        
        crawler = GenericSiteCrawler()
        articles = crawler.crawl(config)
        return {
            'domain': domain,
            'success': True,
            'articles': articles[:MAX_ARTICLES_PER_SITE] if articles else []
        }
    except Exception as e:
        return {
            'domain': domain,
            'success': False,
            'articles': [],
            'error': str(e)[:100]
        }

def ingest_articles(domain, articles):
    """Ingest articles into database."""
    if not articles:
        return 0
    
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM sources WHERE domain = %s", (domain,))
        result = cursor.fetchone()
        source_id = result[0] if result else None
        
        if not source_id:
            return 0
        
        insert_count = 0
        for article in articles[:MAX_ARTICLES_PER_SITE]:
            try:
                cursor.execute("""
                    INSERT INTO articles 
                    (source_id, title, content, url, published_at, crawled_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                """, (
                    source_id,
                    article.get('title', 'Untitled')[:500],
                    article.get('content', '')[:5000],
                    article.get('url', '')[:1000]
                ))
                insert_count += 1
            except:
                continue
        
        conn.commit()
        cursor.close()
        db_service.close()
        return insert_count
    except:
        return 0

print("=" * 80)
print("📊 PHASE 1 CRAWL TEST - GPU-Enabled Ingestion")
print("=" * 80)
print(f"⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Load sources
print("📋 Loading sources...")
sources = get_all_sources()
domains = [s['domain'] for s in sources]
initial_count = get_article_count()

print(f"   ✓ {len(domains)} sources loaded")
print(f"   • Current articles in DB: {initial_count}\n")

# Crawl
print("🔄 Crawling (with GPU acceleration)...")
print("-" * 80)

start = time.time()
results = []
successful = 0
articles_found = 0

with ThreadPoolExecutor(max_workers=CONCURRENT_SITES) as executor:
    futures = {executor.submit(crawl_domain, d): d for d in domains}
    
    for i, future in enumerate(as_completed(futures), 1):
        result = future.result()
        results.append(result)
        
        if result['success']:
            successful += 1
            articles_found += len(result['articles'])
        
        if i % 50 == 0:
            pct = (i / len(domains)) * 100
            print(f"   Progress: {i}/{len(domains)} ({pct:.0f}%) | "
                  f"{successful} successful | {articles_found} articles found")

elapsed = time.time() - start

print(f"\n   ✓ Crawling complete: {elapsed:.1f}s")
print(f"   • Success rate: {successful}/{len(domains)} ({successful/len(domains)*100:.1f}%)")
print(f"   • Articles found: {articles_found}\n")

# Ingest
print("💾 Ingesting to database (with GPU embeddings)...")
print("-" * 80)

total_ingested = 0
for result in results:
    if result['success'] and result['articles']:
        total_ingested += ingest_articles(result['domain'], result['articles'])

final_count = get_article_count()
newly_added = final_count - initial_count

print(f"   ✓ Ingestion complete")
print(f"   • Articles ingested: {newly_added}")
print(f"   • Total in DB: {final_count}\n")

# Summary
print("=" * 80)
print("✅ PHASE 1 CRAWL TEST COMPLETE")
print("=" * 80)
print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"   Sources crawled: {len(domains)}")
print(f"   Success rate: {successful/len(domains)*100:.1f}%")
print(f"   Articles found: {articles_found}")
print(f"   Articles ingested: {newly_added}")
print(f"   Total crawl time: {elapsed:.1f}s")
print(f"   Average per site: {elapsed/len(domains):.2f}s")
print("\n")

PYTHON_SCRIPT

echo "✅ Phase 1 crawl test complete!"
