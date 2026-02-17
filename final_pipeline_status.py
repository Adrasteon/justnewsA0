#!/usr/bin/env python3
"""
Final comprehensive pipeline status check after crawl execution.
"""
import os
import sys
import time

sys.path.insert(0, os.getcwd())
os.environ['JUSTNEWS_DISABLE_TEST_DB_FALLBACK'] = '1'

from database.utils.migrated_database_utils import create_database_service

def check_status():
    db = create_database_service()
    db.ensure_conn()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    print("\n" + "="*80)
    print("JUSTNEWS PIPELINE - FINAL STATUS REPORT")
    print("="*80)
    
    # Crawling metrics
    cursor.execute("SELECT COUNT(*) FROM crawler_tasks")
    crawl_tasks = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM crawler_task_articles")
    found_articles = cursor.fetchone()[0]
    
    # Ingestion metrics
    cursor.execute("SELECT COUNT(*) FROM articles")
    ingested_articles = cursor.fetchone()[0]
    
    # Embeddings
    cursor.execute("SELECT COUNT(*) FROM embeddings_document")
    embeddings = cursor.fetchone()[0]
    
    # Check articles table schema
    cursor.execute("""
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_NAME='articles' AND COLUMN_NAME='last_crawl_at'
    """)
    has_last_crawl_at = cursor.fetchone()[0]
    
    print(f"\n📊 CRAWLING PHASE:")
    print(f"   Crawl Tasks:              {crawl_tasks:>8}")
    print(f"   Articles Found:           {found_articles:>8}")
    
    print(f"\n📰 INGESTION PHASE:")
    print(f"   Articles Ingested:        {ingested_articles:>8}")
    print(f"   Schema Ready:             {'✅ YES' if has_last_crawl_at else '❌ NO'}")
    
    print(f"\n🔍 EMBEDDINGS PHASE:")
    print(f"   Documents Embedded:       {embeddings:>8}")
    
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
