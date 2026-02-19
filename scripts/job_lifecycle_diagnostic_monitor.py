#!/usr/bin/env python3
import json
import os
import time

import mysql.connector
from dotenv import load_dotenv

load_dotenv('/app/global.env')

POLL_SECONDS = int(os.getenv('JOB_LIFECYCLE_POLL_SECONDS', '20'))


def get_conn():
    return mysql.connector.connect(
        host=os.getenv('MARIADB_HOST', 'mariadb'),
        port=int(os.getenv('MARIADB_PORT', '3306')),
        user=os.getenv('MARIADB_USER', 'justnews'),
        password=os.getenv('MARIADB_PASSWORD', 'dev_justnews_password'),
        database=os.getenv('MARIADB_DB', 'justnews'),
    )


def parse_result_metrics(raw_result):
    if raw_result is None:
        return 0, 0, None
    try:
        payload = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
    except Exception:
        return 0, 0, 'invalid_json'

    ingested = int(payload.get('articles_ingested', payload.get('total_articles', 0)) or 0)
    attempted = int(payload.get('total_articles_attempted', 0) or 0)
    exhaustion = payload.get('site_exhaustion')
    exhaustion_hint = None
    if isinstance(exhaustion, dict) and exhaustion:
        exhaustion_hint = ','.join(sorted(set(str(v) for v in exhaustion.values() if v)))
    return ingested, attempted, exhaustion_hint


print('JOB_LIFECYCLE_DIAGNOSTIC_MONITOR_START')
seen = set()

while True:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute(
        '''
        SELECT job_id, status, created_at, updated_at, LEFT(COALESCE(error_message,''),220), result
        FROM crawler_jobs
        ORDER BY created_at DESC
        LIMIT 60
        '''
    )
    rows = cur.fetchall()

    status_counts = {}
    for _, status, *_ in rows:
        key = str(status).lower()
        status_counts[key] = status_counts.get(key, 0) + 1

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] status_counts={status_counts}")

    for job_id, status, created_at, updated_at, error_message, result in rows:
        key = (job_id, str(status).lower())
        if key in seen:
            continue
        seen.add(key)

        if str(status).lower() in {'completed', 'failed', 'cancelled'}:
            ingested, attempted, exhaustion_hint = parse_result_metrics(result)
            print(
                f"JOB_EVENT id={job_id} status={status} created={created_at} updated={updated_at} "
                f"attempted={attempted} ingested={ingested} exhaustion={exhaustion_hint} "
                f"error={error_message or ''}"
            )

    cur.execute('SELECT COUNT(*) FROM articles')
    article_count = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM sources WHERE last_crawl_at IS NOT NULL')
    sources_crawled = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM sources')
    sources_total = cur.fetchone()[0]
    print(
        f"PIPELINE article_count={article_count} sources_crawled={sources_crawled}/{sources_total}"
    )

    cur.close()
    conn.close()
    time.sleep(POLL_SECONDS)
