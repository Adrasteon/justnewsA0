#!/usr/bin/env python3
"""
Comprehensive JustNews system status report with workflow progress tracking.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())
os.environ['JUSTNEWS_DISABLE_TEST_DB_FALLBACK'] = '1'

from database.utils.migrated_database_utils import create_database_service

def format_number(num):
    """Format large numbers with thousands separator."""
    return f"{num:,}"

def check_status():
    db = create_database_service()
    db.ensure_conn()
    conn = db.get_connection()
    cursor = conn.cursor()
    
    print("\n" + "="*90)
    print(" " * 20 + "JUSTNEWS SYSTEM STATUS REPORT")
    print("="*90)
    print(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("="*90)
    
    # ============ SOURCES ============
    cursor.execute("SELECT COUNT(*) FROM sources")
    sources_total = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM sources WHERE last_crawl_at IS NOT NULL
    """)
    sources_crawled = cursor.fetchone()[0]
    
    print(f"\n🔗 SOURCES CONFIGURATION:")
    print(f"   Total Sources Configured:     {format_number(sources_total):>12}")
    print(f"   → Previously Crawled:         {format_number(sources_crawled):>12}")
    print(f"   → Awaiting First Crawl:       {format_number(sources_total - sources_crawled):>12}")
    
    # ============ CRAWLING ============
    cursor.execute("SELECT COUNT(*) FROM crawler_tasks")
    crawler_tasks = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT status, COUNT(*) as count 
        FROM crawler_tasks 
        GROUP BY status
    """)
    tasks_by_status = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM crawler_task_articles")
    articles_discovered = cursor.fetchone()[0]
    
    print(f"\n🕷️  CRAWLING PHASE:")
    print(f"   Crawler Tasks Created:        {format_number(crawler_tasks):>12}")
    for status, count in tasks_by_status:
        print(f"   → Task Status '{status}':            {format_number(count):>12}")
    print(f"   Articles Discovered:          {format_number(articles_discovered):>12}")
    
    # ============ INGESTION ============
    cursor.execute("SELECT COUNT(*) FROM articles")
    articles_ingested = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM articles 
        WHERE embedded = 1
    """)
    articles_embedded = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM articles 
        WHERE analyzed = 1
    """)
    articles_analyzed = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM articles 
        WHERE is_synthesized = 1
    """)
    articles_synthesized = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT COUNT(*) FROM articles 
        WHERE is_published = 1
    """)
    articles_published = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM pending_articles_pool")
    pending_articles = cursor.fetchone()[0]
    
    print(f"\n📰 INGESTION PHASE:")
    print(f"   Articles Ingested:            {format_number(articles_ingested):>12}")
    print(f"   → Embedded:                   {format_number(articles_embedded):>12}")
    print(f"   → Analyzed:                   {format_number(articles_analyzed):>12}")
    print(f"   → Synthesized:                {format_number(articles_synthesized):>12}")
    print(f"   → Published:                  {format_number(articles_published):>12}")
    print(f"   Pending for Processing:       {format_number(pending_articles):>12}")
    
    # ============ EMBEDDINGS ============
    cursor.execute("SELECT COUNT(*) FROM embeddings_document")
    embeddings = cursor.fetchone()[0]
    
    print(f"\n🧠 EMBEDDINGS PHASE:")
    print(f"   Documents Embedded:           {format_number(embeddings):>12}")
    print(f"   → Synced with Articles:       {format_number(articles_embedded):>12}")
    
    # ============ ENTITIES & ANALYSIS ============
    cursor.execute("SELECT COUNT(*) FROM entities")
    entities_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM bias_analysis")
    bias_analyses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sentiment_analysis")
    sentiment_analyses = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM article_entities")
    article_entities = cursor.fetchone()[0]
    
    needs_review_count = articles_ingested - articles_analyzed
    
    print(f"\n🔬 ANALYSIS PHASE:")
    print(f"   Entities Extracted:           {format_number(entities_count):>12}")
    print(f"   Article-Entity Links:         {format_number(article_entities):>12}")
    print(f"   Bias Analyses Performed:      {format_number(bias_analyses):>12}")
    print(f"   Sentiment Analyses:           {format_number(sentiment_analyses):>12}")
    print(f"   Awaiting Review:              {format_number(needs_review_count):>12}")
    
    # ============ AGGREGATION ============
    cursor.execute("SELECT COUNT(*) FROM living_stories")
    living_stories = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM story_updates")
    story_updates = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM synthesized_articles")
    synthesized = cursor.fetchone()[0]
    
    print(f"\n🎯 AGGREGATION PHASE:")
    print(f"   Living Stories Created:       {format_number(living_stories):>12}")
    print(f"   Story Updates:                {format_number(story_updates):>12}")
    print(f"   Synthesized Articles:         {format_number(synthesized):>12}")
    
    # ============ WORKFLOW SUMMARY ============
    print(f"\n{'='*90}")
    print("📊 WORKFLOW PROGRESS SUMMARY:")
    print(f"{'='*90}")
    
    if sources_total == 0:
        print("⚠️  NO SOURCES CONFIGURED - System is ready but awaiting source setup")
    elif crawler_tasks == 0:
        print("⏳ PHASE 1/5: Sources configured, waiting for crawler initiation")
    elif articles_discovered == 0:
        print("🔄 PHASE 2/5: Crawler running but hasn't discovered any articles yet")
    elif articles_ingested == 0:
        print("🔄 PHASE 2/5: Articles discovered, awaiting ingestion")
    elif articles_embedded == 0:
        print("🔄 PHASE 3/5: Articles ingested, awaiting embedding generation")
    elif entities_count == 0:
        print("🔄 PHASE 4/5: Embeddings complete, awaiting entity extraction")
    elif living_stories == 0:
        print("🔄 PHASE 4/5: Analysis complete, awaiting story aggregation")
    else:
        print("✅ PHASE 5/5: Complete pipeline execution - all phases active")
        if articles_discovered > 0:
            ingestion_rate = (articles_ingested / articles_discovered) * 100
            print(f"   Ingestion Rate:               {ingestion_rate:.1f}% ({articles_ingested}/{articles_discovered})")
        if articles_ingested > 0:
            embedding_rate = (articles_embedded / articles_ingested) * 100
            print(f"   Embedding Rate:               {embedding_rate:.1f}% ({articles_embedded}/{articles_ingested})")
        if articles_embedded > 0:
            analysis_rate = (articles_analyzed / articles_embedded) * 100
            print(f"   Analysis Rate:                {analysis_rate:.1f}% ({articles_analyzed}/{articles_embedded})")
    
    print(f"\n{'='*90}\n")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    check_status()
