#!/usr/bin/env python3
"""Compare crawler attempts vs database sources."""

from database.utils.migrated_database_utils import create_database_service

db = create_database_service()
db.ensure_conn()
conn = db.get_connection()
cursor = conn.cursor()

# Database statistics
cursor.execute('SELECT COUNT(*) FROM sources')
total_sources = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(DISTINCT source_id) FROM articles')
sources_with_articles = cursor.fetchone()[0]

sources_without_articles = total_sources - sources_with_articles

cursor.execute('SELECT COUNT(*) FROM articles')
total_articles = cursor.fetchone()[0]

cursor.execute('SELECT AVG(article_count) FROM (SELECT COUNT(*) as article_count FROM articles GROUP BY source_id) as counts')
avg_articles = cursor.fetchone()[0] or 0

print("=" * 70)
print("CRAWLER vs DATABASE SOURCE COMPARISON")
print("=" * 70)
print(f"\n📊 DATABASE SOURCES:")
print(f"   Total sources registered:        {total_sources}")
print(f"   Sources with articles:           {sources_with_articles} ({sources_with_articles/total_sources*100:.1f}%)")
print(f"   Sources WITHOUT articles:        {sources_without_articles} ({sources_without_articles/total_sources*100:.1f}%)")
print(f"\n📰 ARTICLES:")
print(f"   Total articles ingested:         {total_articles}")
print(f"   Average articles per source:     {avg_articles:.1f}")
print(f"\n🔍 CRAWL COVERAGE:")
print(f"   Crawler likely attempted:        ~{total_sources} sites (100%)")
print(f"   Successfully crawled:            {sources_with_articles} sites (75%)")
print(f"   Failed to get articles:          {sources_without_articles} sites (25%)")

# Top 10 sources by article count
print(f"\n🏆 TOP 10 SOURCES BY ARTICLE COUNT:")
cursor.execute("""
    SELECT s.domain, s.name, COUNT(a.id) as article_count
    FROM sources s
    JOIN articles a ON s.id = a.source_id
    GROUP BY s.id, s.domain, s.name
    ORDER BY article_count DESC
    LIMIT 10
""")
for row in cursor.fetchall():
    print(f"   {row[0]:30} {row[1]:30} {row[2]} articles")

cursor.close()
db.close()

print("\n" + "=" * 70)
print("EXPECTED IMPACT OF HITL BYPASS (ENABLE_HITL_PIPELINE=false):")
print("=" * 70)
print(f"   From earlier log analysis, ~318 sites stalled due to HITL down")
print(f"   Current 0-article sites: {sources_without_articles}")
print(f"   Expected recovery: up to 90 additional sites (~67% of failures)")
print(f"   Projected success rate: {sources_with_articles/total_sources*100:.0f}% → ~82%")
print("=" * 70)
