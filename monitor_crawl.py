#!/usr/bin/env python3
"""Real-time monitoring of crawl job progress."""

import json
import time
import subprocess
from datetime import datetime
from database.utils.migrated_database_utils import create_database_service

JOB_ID = "e9cfeac24ee3402aa94e01a38e41efbe"

def get_job_status():
    """Fetch job status from crawler agent."""
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                f"http://localhost:8015/job/{JOB_ID}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None


def get_article_count():
    """Get current article count from database."""
    try:
        db = create_database_service()
        db.ensure_conn()
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM articles")
        count = cursor.fetchone()[0]
        cursor.close()
        db.close()
        return count
    except Exception:
        return None


def get_sources_with_articles():
    """Get count of sources with articles."""
    try:
        db = create_database_service()
        db.ensure_conn()
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT source_id) FROM articles")
        count = cursor.fetchone()[0]
        cursor.close()
        db.close()
        return count
    except Exception:
        return None


def get_recent_logs(lines=5):
    """Get recent crawler log entries."""
    try:
        result = subprocess.run(
            ["tail", "-n", str(lines), "/tmp/crawler_batch.log"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip().split("\n")
    except Exception:
        pass
    return []


print("=" * 80)
print("REAL-TIME CRAWL MONITORING")
print(f"Job ID: {JOB_ID}")
print("=" * 80)

start_time = time.time()
prev_article_count = get_article_count() or 0
prev_source_count = get_sources_with_articles() or 0

print(f"\n📊 BASELINE (t=0):")
print(f"   Articles: {prev_article_count}")
print(f"   Sources with articles: {prev_source_count}")

iteration = 0
while True:
    iteration += 1
    elapsed = time.time() - start_time

    job_status = get_job_status()
    article_count = get_article_count() or 0
    source_count = get_sources_with_articles() or 0

    articles_gained = article_count - prev_article_count
    sources_gained = source_count - prev_source_count

    print(f"\n⏱️  [{elapsed:.0f}s] Iteration {iteration}")
    print(f"   Job Status: {job_status.get('status', 'UNKNOWN') if job_status else 'UNKNOWN'}")
    print(
        f"   Articles: {article_count:,} (+{articles_gained:,} this interval)"
    )
    print(
        f"   Sources: {source_count:,} (+{sources_gained:,} this interval)"
    )
    
    if articles_gained > 0:
        rate = articles_gained / (elapsed / 60) if elapsed > 0 else 0
        print(f"   Rate: {rate:.1f} articles/min")

    # Show job result if done
    if job_status and job_status.get("status") == "completed":
        print(f"\n✅ CRAWL COMPLETED!")
        print(f"   Result: {job_status.get('result', {})}")
        break

    if job_status and job_status.get("status") == "failed":
        print(f"\n❌ CRAWL FAILED!")
        print(f"   Error: {job_status.get('error', 'Unknown error')}")
        break

    # Show recent log lines
    logs = get_recent_logs(2)
    if logs and logs[0].strip():
        print(f"   Latest log: {logs[0][-60:]}")

    prev_article_count = article_count
    prev_source_count = source_count

    time.sleep(30)  # Check every 30 seconds

print("\n" + "=" * 80)
