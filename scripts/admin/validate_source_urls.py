#!/usr/bin/env python
"""
Validate source URLs and health checks.
Tests connectivity for all 500+ sources, identifies dead links, and tracks viability.
"""

import os
import sys
import requests
from urllib.parse import urljoin
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

sys.path.insert(0, os.getcwd())

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service

logger = get_logger("validate_urls")

# Session for connection pooling
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})


def validate_url(source_id: int, domain: str, url: str, timeout: int = 10) -> dict:
    """
    Test a single URL for connectivity and accessibility.
    
    Returns dict with: {
        'source_id': int,
        'domain': str, 
        'url': str,
        'status': 'alive' | 'redirect' | 'timeout' | 'error' | 'offline',
        'status_code': int or None,
        'redirect_to': str or None,
        'error': str or None,
        'response_time': float or None
    }
    """
    result = {
        'source_id': source_id,
        'domain': domain,
        'url': url,
        'status': 'unknown',
        'status_code': None,
        'redirect_to': None,
        'error': None,
        'response_time': None
    }
    
    try:
        start = time.time()
        resp = session.head(url, timeout=timeout, allow_redirects=True, verify=False)
        elapsed = time.time() - start
        
        result['response_time'] = elapsed
        result['status_code'] = resp.status_code
        
        # Check for redirect
        if len(resp.history) > 0:
            result['status'] = 'redirect'
            result['redirect_to'] = resp.url
            if resp.status_code >= 400:
                result['status'] = 'error'
        elif 200 <= resp.status_code < 300:
            result['status'] = 'alive'
        elif 300 <= resp.status_code < 400:
            result['status'] = 'redirect'
            result['redirect_to'] = resp.headers.get('Location', 'unknown')
        elif resp.status_code == 401 or resp.status_code == 403:
            # Might be behind auth/paywall but technically accessible
            result['status'] = 'alive'
            result['error'] = f"Access denied ({resp.status_code})"
        else:
            result['status'] = 'error'
            result['error'] = f"HTTP {resp.status_code}"
            
    except requests.Timeout:
        result['status'] = 'timeout'
        result['error'] = 'Connection timeout'
    except requests.ConnectionError:
        result['status'] = 'offline'
        result['error'] = 'Connection failed'
    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:100]
    
    return result


def validate_all_sources(max_workers: int = 10, batch_size: int = 50):
    """
    Validate all sources in database.
    """
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor(dictionary=True)
        
        # Get all sources
        cursor.execute("SELECT id, domain, url FROM sources ORDER BY id")
        sources = cursor.fetchall()
        total = len(sources)
        
        logger.info(f"Starting validation of {total} sources...")
        print(f"🔍 Validating {total} sources...\n")
        
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(validate_url, s['id'], s['domain'], s['url']): s 
                for s in sources
            }
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                result = future.result()
                results.append(result)
                
                # Progress indicator every 50 sources
                if completed % batch_size == 0:
                    percentage = (completed / total) * 100
                    print(f"Progress: {completed}/{total} ({percentage:.1f}%)", end='\r')
        
        print(f"\n✅ Validation complete for all {total} sources\n")
        return results
        
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise
    finally:
        cursor.close()
        db_service.close()


def generate_report(results: list[dict]):
    """
    Generate and display validation report.
    """
    # Categorize results
    alive = [r for r in results if r['status'] == 'alive']
    redirect = [r for r in results if r['status'] == 'redirect']
    timeout = [r for r in results if r['status'] == 'timeout']
    offline = [r for r in results if r['status'] == 'offline']
    error = [r for r in results if r['status'] == 'error']
    
    total = len(results)
    
    print("=" * 80)
    print("📊 URL VALIDATION REPORT")
    print("=" * 80)
    print(f"\n⏰ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📈 Total sources checked: {total}\n")
    
    print("🟢 STATUS BREAKDOWN")
    print("-" * 80)
    print(f"  ✅ Alive & Accessible:     {len(alive):4d} ({len(alive)/total*100:5.1f}%)")
    print(f"  🔄 Redirects Active:       {len(redirect):4d} ({len(redirect)/total*100:5.1f}%)")
    print(f"  ⏱️  Timeout (slow/blocked): {len(timeout):4d} ({len(timeout)/total*100:5.1f}%)")
    print(f"  🔴 Offline:                {len(offline):4d} ({len(offline)/total*100:5.1f}%)")
    print(f"  ❌ Error:                  {len(error):4d} ({len(error)/total*100:5.1f}%)")
    
    print("\n🟡 ISSUES REQUIRING ATTENTION")
    print("-" * 80)
    
    problematic = offline + timeout + error
    if len(problematic) > 0:
        print(f"Found {len(problematic)} sources with issues:\n")
        for r in problematic[:20]:  # Show top 20
            status_emoji = "🔴" if r['status'] == 'offline' else "⏱️" if r['status'] == 'timeout' else "❌"
            print(f"  {status_emoji} [{r['domain']}] {r['status'].upper()}")
            if r['error']:
                print(f"     └─ {r['error']}")
        
        if len(problematic) > 20:
            print(f"\n  ... and {len(problematic) - 20} more issues")
    else:
        print("  ✨ All sources are accessible!")
    
    print("\n📋 RESPONSE TIME STATISTICS")
    print("-" * 80)
    response_times = [r['response_time'] for r in results if r['response_time'] is not None]
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        print(f"  Average response time: {avg_time:.2f}s")
        print(f"  Fastest: {min_time:.2f}s")
        print(f"  Slowest: {max_time:.2f}s")
    
    print("\n" + "=" * 80)
    
    return {
        'total': total,
        'alive': len(alive),
        'redirect': len(redirect),
        'timeout': len(timeout),
        'offline': len(offline),
        'error': len(error),
        'problematic': problematic
    }


def update_database(results: list[dict]):
    """
    Update database with latest verification results.
    """
    try:
        db_service = create_database_service()
        conn = db_service.mb_conn
        cursor = conn.cursor()
        
        update_query = """
        UPDATE sources 
        SET last_verified = NOW(),
            metadata = JSON_SET(
                COALESCE(metadata, '{}'),
                '$.last_check_status', %s,
                '$.last_check_response_code', %s
            )
        WHERE id = %s
        """
        
        for result in results:
            cursor.execute(update_query, (
                result['status'],
                result['status_code'],
                result['source_id']
            ))
        
        conn.commit()
        logger.info(f"Updated {len(results)} source verification records")
        print(f"✅ Database updated with verification results")
        
    except Exception as e:
        logger.error(f"Database update error: {e}")
    finally:
        cursor.close()
        db_service.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate all source URLs')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers')
    parser.add_argument('--update-db', action='store_true', help='Update database with results')
    args = parser.parse_args()
    
    # Run validation
    results = validate_all_sources(max_workers=args.workers)
    
    # Generate report
    summary = generate_report(results)
    
    # Update database if requested
    if args.update_db:
        update_database(results)
        print("\n💾 Results saved to database")
    
    # Exit code based on issues
    if summary['offline'] > 0 or summary['error'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)
