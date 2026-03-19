#!/usr/bin/env python3
"""
Final comprehensive pipeline status check after crawl execution.
"""
import os
import sys
import time

import mysql.connector
from dotenv import load_dotenv

sys.path.insert(0, os.getcwd())
os.environ['JUSTNEWS_DISABLE_TEST_DB_FALLBACK'] = '1'

load_dotenv('/app/global.env')


def get_db_conn():
    host = os.getenv('MARIADB_HOST', 'mariadb')
    port = int(os.getenv('MARIADB_PORT', 3306))
    user = os.getenv('MARIADB_USER', 'justnews')
    password = os.getenv('MARIADB_PASSWORD', 'dev_justnews_password')
    database = os.getenv('MARIADB_DB', 'justnews')
    return mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )

def check_status():
    conn = get_db_conn()
    cursor = conn.cursor()
    
    print("\n" + "="*80)
    print("JUSTNEWS PIPELINE - FINAL STATUS REPORT")
    print("="*80)
    
    # Crawling metrics (support both legacy and current schemas)
    cursor.execute("SHOW TABLES LIKE 'crawler_tasks'")
    has_crawler_tasks = cursor.fetchone() is not None
    cursor.execute("SHOW TABLES LIKE 'crawler_task_articles'")
    has_crawler_task_articles = cursor.fetchone() is not None

    crawl_tasks_legacy = 0
    if has_crawler_tasks:
        cursor.execute("SELECT COUNT(*) FROM crawler_tasks")
        crawl_tasks_legacy = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM crawler_jobs")
    crawl_tasks_jobs = cursor.fetchone()[0]
    crawl_tasks = max(crawl_tasks_legacy, crawl_tasks_jobs)

    # Source coverage metrics
    cursor.execute("SELECT COUNT(*) FROM sources")
    sources_total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sources WHERE last_crawl_at IS NOT NULL")
    sources_crawled = cursor.fetchone()[0]

    sources_with_articles = 0
    cursor.execute("""
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME='articles'
          AND COLUMN_NAME='source_id'
    """)
    has_source_id = cursor.fetchone()[0] > 0
    if has_source_id:
        cursor.execute("SELECT COUNT(DISTINCT source_id) FROM articles WHERE source_id IS NOT NULL")
        sources_with_articles = cursor.fetchone()[0]

    found_articles_legacy = 0
    if has_crawler_task_articles:
        cursor.execute("SELECT COUNT(*) FROM crawler_task_articles")
        found_articles_legacy = cursor.fetchone()[0]
    # Best available proxy in newer flows
    cursor.execute("SELECT COUNT(*) FROM articles")
    found_articles_current = cursor.fetchone()[0]
    found_articles = max(found_articles_legacy, found_articles_current)
    
    # Ingestion metrics
    cursor.execute("SELECT COUNT(*) FROM articles")
    ingested_articles = cursor.fetchone()[0]
    
    # Embeddings (prefer current articles.embedded flag; fallback to legacy table)
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME='articles'
          AND COLUMN_NAME='embedded'
    """)
    has_embedded_column = cursor.fetchone()[0] > 0

    article_embedded = 0
    if has_embedded_column:
        cursor.execute("SELECT COUNT(*) FROM articles WHERE embedded = 1")
        article_embedded = cursor.fetchone()[0]

    cursor.execute("SHOW TABLES LIKE 'embeddings_document'")
    has_embeddings_table = cursor.fetchone() is not None
    embeddings_document_count = 0
    if has_embeddings_table:
        cursor.execute("SELECT COUNT(*) FROM embeddings_document")
        embeddings_document_count = cursor.fetchone()[0]

    embeddings = max(article_embedded, embeddings_document_count)

    # Fact-check progression (article-level is authoritative for current shim persistence)
    cursor.execute("SELECT COUNT(*) FROM articles WHERE fact_check_status IS NOT NULL")
    fact_checked_status = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM articles WHERE fact_check_details IS NOT NULL")
    fact_checked_details = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM articles
        WHERE fact_check_status IS NOT NULL
          AND updated_at >= (NOW() - INTERVAL 60 MINUTE)
        """
    )
    fact_checked_status_last60m = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM articles
        WHERE fact_check_details IS NOT NULL
          AND updated_at >= (NOW() - INTERVAL 60 MINUTE)
        """
    )
    fact_checked_details_last60m = cursor.fetchone()[0]

    # Legacy/reference metric only.
    cursor.execute("SHOW TABLES LIKE 'fact_checks'")
    has_fact_checks_table = cursor.fetchone() is not None
    fact_checks_table_total = None
    if has_fact_checks_table:
        cursor.execute("SELECT COUNT(*) FROM fact_checks")
        fact_checks_table_total = cursor.fetchone()[0]
    
    # Check articles table schema readiness
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME='articles'
          AND COLUMN_NAME IN ('analyzed', 'embedded', 'fact_check_status', 'input_cluster_ids')
    """)
    schema_feature_count = cursor.fetchone()[0]
    schema_ready = schema_feature_count >= 4
    
    print(f"\n📊 CRAWLING PHASE:")
    print(f"   Crawl Tasks:              {crawl_tasks:>8}")
    print(f"   Articles Found:           {found_articles:>8}")
    print(f"   Sources Crawled:          {sources_crawled:>8}/{sources_total}")
    print(f"   Sources With Articles:    {sources_with_articles:>8}/{sources_total}")
    
    print(f"\n📰 INGESTION PHASE:")
    print(f"   Articles Ingested:        {ingested_articles:>8}")
    print(f"   Schema Ready:             {'✅ YES' if schema_ready else '❌ NO'}")
    
    print(f"\n🔍 EMBEDDINGS PHASE:")
    print(f"   Documents Embedded:       {embeddings:>8}")

    print(f"\n✅ FACT-CHECK PHASE:")
    print(f"   Articles Status Set:      {fact_checked_status:>8}")
    print(f"   Articles Details Set:     {fact_checked_details:>8}")
    print(f"   Status Updates Last 60m:  {fact_checked_status_last60m:>8}")
    print(f"   Detail Updates Last 60m:  {fact_checked_details_last60m:>8}")
    if fact_checks_table_total is not None:
        print(f"   Legacy fact_checks rows:  {fact_checks_table_total:>8} (reference)")
    
    print(f"\n📈 PIPELINE FLOW:")
    if crawl_tasks > 0:
        print(f"   → Crawl starting: ✅")
        if found_articles > 0:
            print(f"   → Article discovery: ✅ ({found_articles} articles found)")
            conv_rate = (ingested_articles / found_articles * 100) if found_articles > 0 else 0
            print(f"   → Ingestion: {'✅' if ingested_articles > 0 else '⏳'} ({conv_rate:.1f}% conversion)")
        else:
            print(f"   → Article discovery: ⏳")
    else:
        print(f"   → Crawl starting: ⏳")
    
    print(f"\n" + "="*80)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    check_status()
