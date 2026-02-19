#!/usr/bin/env python3
import os
import time

import mysql.connector
import requests
from dotenv import load_dotenv

load_dotenv('/app/global.env')
POLL_SECONDS = int(os.getenv('INGEST_MONITOR_POLL_SECONDS', '30'))

crawler_port = os.getenv('CRAWLER_AGENT_PORT', '8022')
crawler_base = f'http://127.0.0.1:{crawler_port}'


def db_snapshot():
    conn = mysql.connector.connect(
        host=os.getenv('MARIADB_HOST', 'mariadb'),
        port=int(os.getenv('MARIADB_PORT', '3306')),
        user=os.getenv('MARIADB_USER', 'justnews'),
        password=os.getenv('MARIADB_PASSWORD', 'dev_justnews_password'),
        database=os.getenv('MARIADB_DB', 'justnews'),
    )
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM articles')
    articles = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM sources WHERE last_crawl_at IS NOT NULL')
    sources_crawled = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM sources')
    sources_total = cur.fetchone()[0]
    cur.close()
    conn.close()
    return articles, sources_crawled, sources_total


print('INGESTION_PROGRESS_MONITOR_START')
start_articles, start_sources_crawled, start_sources_total = db_snapshot()
print(f'initial articles={start_articles} sources_crawled={start_sources_crawled}/{start_sources_total}')

while True:
    try:
        articles, sources_crawled, sources_total = db_snapshot()
        jobs = requests.get(f'{crawler_base}/jobs', timeout=10).json()
        running = sum(1 for s in jobs.values() if str(s).lower() == 'running')
        pending = sum(1 for s in jobs.values() if str(s).lower() == 'pending')
        completed = sum(1 for s in jobs.values() if str(s).lower() == 'completed')
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"articles={articles} delta_articles={articles - start_articles} "
            f"sources_crawled={sources_crawled}/{sources_total} "
            f"delta_sources={sources_crawled - start_sources_crawled} "
            f"running={running} pending={pending} completed={completed}"
        )
    except Exception as exc:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] monitor_error={exc}")

    time.sleep(POLL_SECONDS)
