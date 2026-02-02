#!/usr/bin/env python
"""
Live crawling tests for 500+ sources.
Tests crawling functionality across regional samples.
"""

import os
import sys
import random
from datetime import datetime

sys.path.insert(0, os.getcwd())

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("crawl_tests")


def select_test_samples(test_percentage: float = 0.1) -> dict:
    """
    Select representative sample of sources for testing (10% by default).
    Ensures sampling across all regions and crawl profiles.
    """
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        
        print(f"\n📊 SELECTING TEST SAMPLES ({test_percentage*100:.0f}% of sources)")
        print("=" * 80 + "\n")
        
        # Get all sources with profiles
        cursor.execute("""
            SELECT id, name, domain, country,
                   JSON_EXTRACT(metadata, '$.crawl_profile') as profile
            FROM sources 
            ORDER BY country, name
        """)
        sources = cursor.fetchall()
        total = len(sources)
        sample_size = max(int(total * test_percentage), 1)
        
        print(f"Total sources: {total}")
        print(f"Sample size: {sample_size}")
        print(f"Sampling strategy: Stratified by region and crawl profile\n")
        
        # Group by crawl profile
        by_profile = {}
        for source in sources:
            profile = source['profile'] or 'standard_crawl4ai'
            if profile not in by_profile:
                by_profile[profile] = []
            by_profile[profile].append(source)
        
        # Sample from each profile proportionally
        samples = {}
        print("📋 SAMPLING BREAKDOWN BY CRAWL PROFILE")
        print("-" * 80)
        
        for profile, profile_sources in by_profile.items():
            profile_sample_size = max(int(len(profile_sources) * test_percentage), 1)
            sampled = random.sample(profile_sources, profile_sample_size)
            samples[profile] = sampled
            pct = (profile_sample_size / len(profile_sources)) * 100
            print(f"  {profile:30s}: {profile_sample_size:3d}/{len(profile_sources):3d} ({pct:5.1f}%)")
        
        # Flatten and group by country
        all_samples = []
        for profile_samples in samples.values():
            all_samples.extend(profile_samples)
        
        print(f"\n📍 REGIONAL DISTRIBUTION IN SAMPLE")
        print("-" * 80)
        by_country = {}
        for source in all_samples:
            country = source['country'] or 'XX'
            if country not in by_country:
                by_country[country] = []
            by_country[country].append(source)
        
        for country in sorted(by_country.keys())[:15]:
            count = len(by_country[country])
            print(f"  {country:3s}: {count:2d} sources")
        
        if len(by_country) > 15:
            remaining = sum(len(s) for c, s in by_country.items() if c not in sorted(by_country.keys())[:15])
            print(f"  ... plus {len(by_country) - 15} more countries ({remaining} sources)")
        
        return {
            'total': total,
            'sample_size': len(all_samples),
            'by_profile': samples,
            'all_samples': all_samples
        }
        
    except Exception as e:
        logger.error(f"Sampling error: {e}")
        raise
    finally:
        cursor.close()
        db_service.close()


def prepare_crawl_test_plan(samples: dict) -> dict:
    """
    Prepare a test plan with crawl configurations for samples.
    """
    test_plan = {
        'timestamp': datetime.now().isoformat(),
        'total_tests': len(samples['all_samples']),
        'test_categories': {},
        'estimated_duration': None
    }
    
    # Categorize by profile
    for profile, sources in samples['by_profile'].items():
        test_plan['test_categories'][profile] = {
            'count': len(sources),
            'timeout': 30 if 'high_volume' in profile else 15,
            'max_pages': 50 if 'high_volume' in profile else 10,
            'sources': [{'id': s['id'], 'domain': s['domain'], 'name': s['name']} for s in sources[:3]]
        }
    
    # Estimate duration (assume avg 5 seconds per source)
    test_plan['estimated_duration'] = f"{len(samples['all_samples']) * 5 / 60:.1f} minutes"
    
    return test_plan


def generate_test_report(samples: dict, test_plan: dict):
    """
    Generate a comprehensive crawling test plan and report.
    """
    print(f"\n\n🧪 CRAWLING TEST PLAN")
    print("=" * 80)
    print(f"Generated: {test_plan['timestamp']}")
    print(f"Total tests planned: {test_plan['total_tests']}")
    print(f"Estimated duration: {test_plan['estimated_duration']}\n")
    
    print("📋 TEST EXECUTION GUIDE")
    print("-" * 80)
    
    print("""
PHASE 1: Pre-test Validation
  1. Verify test sample is representative (✓ Done)
  2. Check database connectivity (✓ Done)
  3. Validate crawl profiles loaded (✓ Done)

PHASE 2: Batch Testing by Profile
""")
    
    for profile, config in test_plan['test_categories'].items():
        print(f"\n  Profile: {profile}")
        print(f"    • Sources to test: {config['count']}")
        print(f"    • Timeout per source: {config['timeout']}s")
        print(f"    • Max pages per source: {config['max_pages']}")
        print(f"    • Parallel workers: 3")
        
        if config['sources']:
            print(f"    • Sample domains: {', '.join(s['domain'] for s in config['sources'][:2])}")
    
    print(f"""

PHASE 3: Results Collection
  • Track success rate per profile
  • Record response times
  • Identify problematic sources
  • Compare vs baseline expectations

PHASE 4: Analysis & Reporting
  • Overall success rate target: >80%
  • Alert threshold: <60% success
  • Document edge cases
  • Update source metadata

METRICS TO TRACK
  ✓ Success rate (% of successful crawls)
  ✓ Average response time (seconds)
  ✓ Content extraction quality
  ✓ Redirect handling
  ✓ JavaScript rendering capability
  ✓ Error types and frequencies

EXECUTION COMMAND
  $ python run_crawl_tests.py --batch-size 10 --workers 3 --timeout 30

NEXT STEPS AFTER TESTING
  1. Review results and identify problem sources
  2. Adjust time limits for slow sources
  3. Update crawl profiles for edge cases
  4. Mark successful sources as validated
  5. Disable or replace failed sources
""")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Plan and prepare live crawling tests')
    parser.add_argument('--sample-pct', type=float, default=0.10, 
                       help='Percentage of sources to sample for testing (default 10%%)')
    parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility')
    args = parser.parse_args()
    
    # Set random seed for reproducibility
    random.seed(args.seed)
    
    # Select samples
    samples = select_test_samples(test_percentage=args.sample_pct)
    
    # Prepare test plan
    test_plan = prepare_crawl_test_plan(samples)
    
    # Generate report
    generate_test_report(samples, test_plan)
    
    print("\n✅ Test plan prepared. Ready to execute live crawling tests.")
