#!/usr/bin/env python3
"""
monitor_crawl_progress.py - Monitor the progress of the crawl job

Shows real-time progress of article population
"""

import os
import sys
import time
from datetime import datetime
import mysql.connector

sys.path.insert(0, os.getcwd())

def create_connection():
    """Create a connection to MariaDB"""
    try:
        conn = mysql.connector.connect(
            host=os.environ.get("MARIADB_HOST", "mariadb"),
            port=int(os.environ.get("MARIADB_PORT", 3306)),
            user=os.environ.get("MARIADB_USER", "justnews"),
            password=os.environ.get("MARIADB_PASSWORD", "dev_justnews_password"),
            database=os.environ.get("MARIADB_DB", "justnews"),
        )
        return conn
    except Exception as e:
        print(f"Connection error: {e}")
        return None

def get_article_count(conn):
    """Get current article count"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM articles")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        return 0

def get_source_coverage(conn):
    """Get how many sources have articles"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT source_domain) FROM articles")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        return 0

def get_total_sources(conn):
    """Get total sources"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sources")
        count = cursor.fetchone()[0]
        cursor.close()
        return count
    except Exception as e:
        return 100  # Assume 100

def monitor_crawl(interval=10, duration=None):
    """Monitor crawl progress"""
    print("\n" + "="*70)
    print("🔍 CRAWL PROGRESS MONITOR")
    print("="*70)
    print()
    
    conn = create_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return
    
    start_time = time.time()
    prev_count = 0
    prev_time = start_time
    
    total_sources = get_total_sources(conn)
    
    try:
        while True:
            current_time = time.time()
            elapsed = int(current_time - start_time)
            
            article_count = get_article_count(conn)
            source_coverage = get_source_coverage(conn)
            
            time_delta = current_time - prev_time
            article_delta = article_count - prev_count
            rate = article_delta / time_delta if time_delta > 0 else 0
            
            # Calculate progress bar
            progress_pct = (article_count / 1000) * 100 if article_count > 0 else 0
            bar_length = 40
            filled = int(bar_length * progress_pct / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            # ETA calculation (assuming ~1000 articles target)
            eta_secs = (1000 - article_count) / rate if rate > 0 else 0
            eta_mins = int(eta_secs / 60)
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"\r[{timestamp}] {bar} {article_count:>4} articles | {source_coverage}/{total_sources} sources | "
                  f"+{article_delta}/10s | ETA: {eta_mins}m", end="", flush=True)
            
            prev_count = article_count
            prev_time = current_time
            
            # Check duration limit
            if duration and elapsed >= duration:
                break
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n⏹ Monitoring stopped")
    finally:
        conn.close()
    
    print("\n\n" + "="*70)
    print("📊 FINAL STATISTICS")
    print("="*70)
    
    # Final stats
    conn = create_connection()
    if conn:
        final_count = get_article_count(conn)
        final_coverage = get_source_coverage(conn)
        total_elapsed = int(time.time() - start_time)
        
        print(f"✓ Total articles crawled: {final_count}")
        print(f"✓ Sources with content:   {final_coverage}/{total_sources}")
        print(f"✓ Time elapsed:           {total_elapsed//60}m {total_elapsed%60}s")
        print(f"✓ Average rate:           {final_count/(total_elapsed/60):.1f} articles/min")
        print()
        
        conn.close()

if __name__ == "__main__":
    # Monitor for up to 60 minutes
    monitor_crawl(interval=10, duration=3600)
