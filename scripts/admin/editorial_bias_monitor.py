#!/usr/bin/env python
"""
Editorial bias monitoring and analysis.
Tracks editorial diversity and perspective distribution across sources.
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.getcwd())

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("editorial_bias")


# Editorial angle definitions
EDITORIAL_ANGLES = {
    'state': {'label': 'State-controlled', 'bias': 0, 'examples': ['IRNA', 'TASS', 'China Daily']},
    'commercial_center': {'label': 'Commercial/Center', 'bias': 0, 'examples': ['BBC', 'Reuters', 'AP']},
    'commercial_left': {'label': 'Commercial/Left', 'bias': -1, 'examples': ['MSNBC', 'Guardian', 'Slate']},
    'commercial_right': {'label': 'Commercial/Right', 'bias': 1, 'examples': ['Fox', 'WSJ', 'Economist']},
    'independent': {'label': 'Independent/Center', 'bias': 0, 'examples': ['ProPublica', 'Intercept']},
    'public': {'label': 'Public/Center', 'bias': 0, 'examples': ['BBC', 'PBS', 'RTE']},
    'wire': {'label': 'Wire Service', 'bias': 0, 'examples': ['Reuters', 'AP', 'AFP']},
}


def analyze_editorial_distribution():
    """
    Analyze the distribution of editorial angles across sources.
    """
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        
        print("\n" + "=" * 80)
        print("📊 EDITORIAL BIAS MONITORING")
        print("=" * 80 + "\n")
        
        # Get all sources with country info
        cursor.execute("""
            SELECT id, name, domain, country, 
                   JSON_EXTRACT(metadata, '$.last_check_status') as check_status
            FROM sources 
            ORDER BY country, name
        """)
        sources = cursor.fetchall()
        total = len(sources)
        
        print(f"📈 Total sources: {total}")
        print(f"🌍 Countries represented: (analyzing...)\n")
        
        # Analyze by country
        country_coverage = defaultdict(list)
        for source in sources:
            country = source['country'] or 'XX'
            country_coverage[country].append(source)
        
        print(f"✅ {len(country_coverage)} unique countries\n")
        
        # Show coverage balance
        print("🌐 TOP 15 COUNTRIES BY SOURCE COUNT")
        print("-" * 80)
        sorted_countries = sorted(country_coverage.items(), key=lambda x: -len(x[1]))
        for i, (country, sources_list) in enumerate(sorted_countries[:15], 1):
            pct = (len(sources_list) / total) * 100
            bar = "█" * int(pct / 2)
            print(f"  {i:2d}. {country:3s} | {len(sources_list):3d} sources | {pct:5.1f}% {bar}")
        
        # Single-source analysis
        single_source = [c for c, s in country_coverage.items() if len(s) == 1]
        dual_source = [c for c, s in country_coverage.items() if len(s) == 2]
        multi_source = [c for c, s in country_coverage.items() if len(s) >= 3]
        
        print(f"\n📋 COVERAGE BALANCE")
        print("-" * 80)
        print(f"  Single-source countries:  {len(single_source):3d} ({len(single_source)/len(country_coverage)*100:5.1f}%)")
        print(f"  Dual-source countries:    {len(dual_source):3d} ({len(dual_source)/len(country_coverage)*100:5.1f}%)")
        print(f"  Multi-source countries:   {len(multi_source):3d} ({len(multi_source)/len(country_coverage)*100:5.1f}%)")
        
        # URL health
        cursor.execute("""
            SELECT JSON_EXTRACT(metadata, '$.last_check_status') as status, COUNT(*) as count
            FROM sources
            WHERE metadata IS NOT NULL
            GROUP BY status
        """)
        status_counts = cursor.fetchall()
        
        print(f"\n🔗 SOURCE HEALTH STATUS")
        print("-" * 80)
        for row in status_counts:
            status = row['status'] or 'Not checked'
            count = row['count']
            pct = (count / total) * 100
            print(f"  {status:20s}: {count:4d} ({pct:5.1f}%)")
        
        # Regional stats
        region_stats = defaultdict(lambda: {'count': 0, 'healthy': 0})
        for source in sources:
            country = source['country'] or 'XX'
            region_stats[country]['count'] += 1
            status = source['check_status']
            if status in ['alive', 'redirect']:
                region_stats[country]['healthy'] += 1
        
        print(f"\n✨ MONITORING RECOMMENDATIONS")
        print("-" * 80)
        print(f"""
  1. GEOGRAPHIC BALANCE
     • Maintain 3+ sources per major country (population >50M)
     • Monitor {len(single_source)} single-source countries for redundancy
     • Consider rotating sources in underserved regions

  2. EDITORIAL DIVERSITY
     • Ensure mix of state, commercial, independent outlets per country
     • Track perspective distribution (left/center/right)
     • Monitor for dominance of any single editorial angle

  3. SOURCE HEALTH
     • Currently {sum(1 for s in sources if s['check_status'] in ['alive', 'redirect'])}/{total} sources healthy
     • Run URL validation every 30 days
     • Replace offline sources within 7 days

  4. BIAS DETECTION SYSTEM
     • Implement comparative coverage analysis
     • Track editorial angle representation per major event
     • Alert on >70% concentration in single angle per topic
""")
        
        return True
        
    except Exception as e:
        logger.error(f"Editorial analysis error: {e}")
        raise
    finally:
        cursor.close()
        db_service.close()


def generate_bias_baseline():
    """
    Generate a baseline for editorial bias detection.
    Useful for comparing against future coverage patterns.
    """
    baseline = {
        'timestamp': None,
        'total_sources': 0,
        'country_distribution': {},
        'editorial_angles': {},
        'health_metrics': {
            'alive': 0,
            'redirect': 0,
            'timeout': 0,
            'offline': 0,
            'error': 0
        }
    }
    
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        from datetime import datetime
        
        baseline['timestamp'] = datetime.now().isoformat()
        
        # Total sources
        cursor.execute("SELECT COUNT(*) as count FROM sources")
        baseline['total_sources'] = cursor.fetchone()['count']
        
        # Country distribution
        cursor.execute("""
            SELECT country, COUNT(*) as count FROM sources 
            GROUP BY country ORDER BY count DESC
        """)
        baseline['country_distribution'] = {row['country']: row['count'] for row in cursor.fetchall()}
        
        # Health metrics
        cursor.execute("""
            SELECT JSON_EXTRACT(metadata, '$.last_check_status') as status, COUNT(*) as count
            FROM sources WHERE metadata IS NOT NULL
            GROUP BY status
        """)
        for row in cursor.fetchall():
            status = row['status'] or 'unknown'
            baseline['health_metrics'][status] = row['count']
        
        print("\n📊 EDITORIAL BIAS BASELINE GENERATED")
        print("-" * 80)
        print(f"Timestamp: {baseline['timestamp']}")
        print(f"Total sources: {baseline['total_sources']}")
        print(f"Countries: {len(baseline['country_distribution'])}")
        print(f"Healthy sources: {baseline['health_metrics']['alive'] + baseline['health_metrics']['redirect']}")
        
        return baseline
        
    except Exception as e:
        logger.error(f"Baseline generation error: {e}")
        return None
    finally:
        cursor.close()
        db_service.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor editorial bias and diversity')
    parser.add_argument('--analyze', action='store_true', help='Analyze current editorial distribution')
    parser.add_argument('--baseline', action='store_true', help='Generate bias baseline for comparison')
    args = parser.parse_args()
    
    if args.baseline:
        generate_bias_baseline()
    
    if args.analyze or not args.baseline:
        analyze_editorial_distribution()
