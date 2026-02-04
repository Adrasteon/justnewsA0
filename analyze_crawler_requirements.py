#!/usr/bin/env python3
"""Analyze site-specific crawler requirements."""

from database.utils.migrated_database_utils import create_database_service
import json
from collections import defaultdict

db = create_database_service()
db.ensure_conn()
conn = db.get_connection()
cursor = conn.cursor()

# Get all metadata and analyze it
cursor.execute('SELECT domain, name, metadata FROM sources')
strategies = defaultdict(list)
profiles = defaultdict(list)
has_article_selector = []
has_xpath = []
has_custom_selector = []

for row in cursor.fetchall():
    domain, name, meta_str = row
    try:
        meta = json.loads(meta_str)
        
        # Track strategies
        if 'crawling_strategy' in meta:
            strategies[meta['crawling_strategy']].append(domain)
        
        # Track profiles
        if 'crawl_profile' in meta:
            profiles[meta['crawl_profile']].append(domain)
        
        # Check for custom selectors
        if 'selector' in meta or 'article_selector' in meta:
            has_article_selector.append((domain, name, meta))
        
        if 'xpath' in meta:
            has_xpath.append((domain, name, meta))
            
        if 'custom_selector' in meta:
            has_custom_selector.append((domain, name, meta))
    except:
        pass

print("=" * 80)
print("SITE-SPECIFIC CRAWLER REQUIREMENTS")
print("=" * 80)

print("\n📊 CRAWLING STRATEGIES:")
for strat, domains in sorted(strategies.items()):
    pct = len(domains)/541*100
    print(f"  {strat:30} {len(domains):3} sites ({pct:.0f}%)")

print("\n📊 CRAWL PROFILES:")
for profile, domains in sorted(profiles.items()):
    print(f"  {profile:30} {len(domains):3} sites")

if not strategies and not profiles:
    print("  (No strategy or profile specified)")

print("\n🔧 CUSTOM SELECTORS/XPATH:")
print(f"  Sources with article_selector:   {len(has_article_selector)}")
print(f"  Sources with xpath:              {len(has_xpath)}")
print(f"  Sources with custom_selector:    {len(has_custom_selector)}")

if has_article_selector:
    print("\n  Examples with article selectors:")
    for domain, name, meta in has_article_selector[:3]:
        print(f"    {domain} ({name})")
        if 'article_selector' in meta:
            print(f"      → {meta['article_selector']}")

if has_xpath:
    print("\n  Examples with xpath:")
    for domain, name, meta in has_xpath[:3]:
        print(f"    {domain} ({name})")
        print(f"      → {meta.get('xpath')}")

print("\n" + "=" * 80)

cursor.close()
db.close()
