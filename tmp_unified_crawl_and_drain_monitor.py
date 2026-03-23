#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mysql.connector
import requests


def load_env() -> None:
    env_path = Path('/app/global.env')
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: datetime) -> str:
    return ts.isoformat()


def db_conn():
    return mysql.connector.connect(
        host=os.environ.get('MARIADB_HOST', 'localhost'),
        user=os.environ.get('MARIADB_USER'),
        password=os.environ.get('MARIADB_PASSWORD'),
        database=os.environ.get('MARIADB_DB'),
        autocommit=True,
        connection_timeout=10,
    )


def detect_crawler_base() -> str:
    for port in (8022, 8015):
        try:
            r = requests.get(f'http://localhost:{port}/health', timeout=2)
            if r.status_code == 200:
                return f'http://localhost:{port}'
        except Exception:
            pass
    raise RuntimeError('crawler health endpoint not reachable on 8022/8015')


def auth_headers() -> dict[str, str]:
    token = os.environ.get('CRAWLER_API_TOKEN', '').strip()
    if token:
        return {'Authorization': f'Bearer {token}'}
    return {}


def fetch_domains(limit: int = 24) -> list[str]:
    conn = db_conn()
    cur = conn.cursor()
    try:
        cur.execute('DESCRIBE sources')
        cols = {r[0] for r in cur.fetchall()}
        order_col = 'last_crawl_at' if 'last_crawl_at' in cols else ('created_at' if 'created_at' in cols else 'id')
        cur.execute(
            f"""
            SELECT domain
            FROM sources
            WHERE domain IS NOT NULL AND domain != ''
            ORDER BY COALESCE({order_col}, '1970-01-01') ASC
            LIMIT %s
            """,
            (limit,),
        )
        return [r[0] for r in cur.fetchall() if r and r[0]]
    finally:
        cur.close()
        conn.close()


def snapshot_metrics(run_start: datetime) -> dict[str, Any]:
    conn = db_conn()
    cur = conn.cursor()
    try:
        q = {}
        cur.execute('SELECT COUNT(*) FROM articles')
        q['articles_total'] = int(cur.fetchone()[0])

        cur.execute('SELECT COUNT(*) FROM articles WHERE analyzed = 0')
        q['queue_analyze'] = int(cur.fetchone()[0])

        cur.execute('SELECT COUNT(*) FROM articles WHERE analyzed = 1 AND embedded = 0')
        q['queue_embed'] = int(cur.fetchone()[0])

        cur.execute("""
            SELECT COUNT(*)
            FROM articles
            WHERE analyzed = 1
              AND (fact_check_status IS NULL OR fact_check_status = '')
        """)
        q['queue_fact_check'] = int(cur.fetchone()[0])

        cur.execute("""
            SELECT COUNT(*)
            FROM articles
            WHERE embedded = 1
              AND fact_check_status IS NOT NULL
              AND fact_check_status != ''
              AND (input_cluster_ids IS NULL OR input_cluster_ids = '' OR input_cluster_ids = '[]')
        """)
        q['queue_cluster_assign'] = int(cur.fetchone()[0])

        cur.execute("""
            SELECT COUNT(*)
            FROM articles
            WHERE is_synthesized = 0
              AND input_cluster_ids IS NOT NULL
              AND input_cluster_ids != ''
              AND input_cluster_ids != '[]'
        """)
        q['queue_synthesis'] = int(cur.fetchone()[0])

        cur.execute("""
            SELECT COUNT(*)
            FROM synthesized_articles
            WHERE is_published = 0
              AND (critique_status IS NULL OR critique_status = 'pending')
        """)
        q['queue_critique'] = int(cur.fetchone()[0])

        cur.execute("""
            SELECT COUNT(*)
            FROM synthesized_articles
            WHERE is_published = 0
              AND critique_status = 'completed'
        """)
        q['queue_publish'] = int(cur.fetchone()[0])

        cur.execute('SELECT COUNT(*) FROM synthesized_articles')
        q['synthesized_total'] = int(cur.fetchone()[0])

        cur.execute('SELECT COUNT(*) FROM synthesized_articles WHERE is_published = 1')
        q['published_total'] = int(cur.fetchone()[0])

        cur.execute('SELECT COUNT(*) FROM news_article')
        q['news_article_total'] = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM synthesized_articles
            WHERE updated_at > created_at
              AND updated_at >= %s
            """,
            (run_start.replace(tzinfo=None),),
        )
        q['living_story_updates_since_start'] = int(cur.fetchone()[0])

        q['queue_total'] = (
            q['queue_analyze']
            + q['queue_embed']
            + q['queue_fact_check']
            + q['queue_cluster_assign']
            + q['queue_synthesis']
            + q['queue_critique']
            + q['queue_publish']
        )

        return q
    finally:
        cur.close()
        conn.close()


def agent_health() -> dict[str, bool]:
    checks = {
        'crawler': 8022,
        'workflow_orchestrator': 8023,
        'analyst': 8004,
        'synthesizer': 8005,
        'critic': 8006,
        'memory': 8007,
        'fact_checker': 8018,
    }
    status = {}
    for name, port in checks.items():
        ok = False
        try:
            r = requests.get(f'http://localhost:{port}/health', timeout=1.5)
            ok = r.status_code == 200
        except Exception:
            ok = False
        status[name] = ok
    return status


def restart_agents_if_needed(health: dict[str, bool]) -> bool:
    essential = ['crawler', 'workflow_orchestrator']
    down = [name for name in essential if not health.get(name, False)]
    if not down:
        return False
    cmd = "bash /app/start_all_services.sh"
    rc = os.system(cmd)
    return rc == 0


def post_crawl(base_url: str, domains: list[str], max_articles_per_site: int, concurrent_sites: int) -> str:
    payload = {
        'args': [domains],
        'kwargs': {
            'domains': domains,
            'max_articles_per_site': max_articles_per_site,
            'concurrent_sites': concurrent_sites,
        },
    }
    r = requests.post(
        f'{base_url}/unified_production_crawl',
        headers=auth_headers(),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get('status') != 'accepted' or not data.get('job_id'):
        raise RuntimeError(f'unexpected crawl submit response: {data}')
    return str(data['job_id'])


def get_job(base_url: str, job_id: str) -> dict[str, Any]:
    r = requests.get(f'{base_url}/job_status/{job_id}', headers=auth_headers(), timeout=15)
    r.raise_for_status()
    out = r.json()
    if isinstance(out, dict):
        return out
    return {'status': 'unknown', 'raw': out}


def main() -> None:
    load_env()
    report_path = Path('/app/tmp_unified_crawl_report.json')
    sample_path = Path('/app/tmp_unified_crawl_samples.jsonl')
    sample_path.unlink(missing_ok=True)

    run_start = now_utc()
    base_url = detect_crawler_base()

    health0 = agent_health()
    restart_attempted = False
    if (not health0.get('crawler', False)) or (not health0.get('workflow_orchestrator', False)):
        restart_attempted = restart_agents_if_needed(health0)
        time.sleep(5)

    domains = fetch_domains(limit=24)
    if not domains:
        raise RuntimeError('no domains available from sources table')

    max_articles_per_site = 13
    concurrent_sites = 6

    baseline = snapshot_metrics(run_start)

    job_id = post_crawl(base_url, domains, max_articles_per_site, concurrent_sites)

    stable_since = None
    last_queue = None
    job_completed_at = None
    job_status = 'pending'
    job_result: dict[str, Any] = {}
    restart_events: list[dict[str, Any]] = []

    while True:
        ts = now_utc()
        health = agent_health()
        if (not health.get('crawler', False)) or (not health.get('workflow_orchestrator', False)):
            restarted = restart_agents_if_needed(health)
            restart_events.append({'time': iso(ts), 'health': health, 'restart': restarted})
            time.sleep(10)

        metrics = snapshot_metrics(run_start)
        job = get_job(base_url, job_id)
        job_status = str(job.get('status', 'unknown')).lower()
        if job_status in {'completed', 'failed', 'cancelled'} and job_completed_at is None:
            job_completed_at = ts
            job_result = job.get('result') if isinstance(job.get('result'), dict) else {}

        row = {
            'time': iso(ts),
            'job_status': job_status,
            'queue_total': metrics['queue_total'],
            'queues': {k: v for k, v in metrics.items() if k.startswith('queue_')},
            'articles_total': metrics['articles_total'],
            'synthesized_total': metrics['synthesized_total'],
            'published_total': metrics['published_total'],
            'living_story_updates_since_start': metrics['living_story_updates_since_start'],
        }
        with sample_path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(row) + '\n')

        queue_now = metrics['queue_total']
        baseline_queue = baseline['queue_total']
        drained_floor = queue_now <= baseline_queue

        if job_status in {'completed', 'failed', 'cancelled'} and drained_floor:
            if last_queue is None or last_queue != queue_now:
                stable_since = ts
            elif stable_since is None:
                stable_since = ts
            elif (ts - stable_since).total_seconds() >= 300:
                break
        else:
            stable_since = None

        last_queue = queue_now

        if job_status in {'failed', 'cancelled'}:
            if job_completed_at and (ts - job_completed_at).total_seconds() >= 90:
                break

        time.sleep(30)

    run_end = now_utc()
    final = snapshot_metrics(run_start)

    elapsed_sec = max((run_end - run_start).total_seconds(), 1.0)
    ingested_delta = final['articles_total'] - baseline['articles_total']
    synthesized_delta = final['synthesized_total'] - baseline['synthesized_total']
    published_delta = final['published_total'] - baseline['published_total']
    living_updates = final['living_story_updates_since_start']

    report = {
        'run': {
            'start': iso(run_start),
            'end': iso(run_end),
            'elapsed_seconds': round(elapsed_sec, 2),
            'elapsed_minutes': round(elapsed_sec / 60.0, 2),
            'crawler_base_url': base_url,
            'job_id': job_id,
            'job_status': job_status,
            'restart_attempted_on_startup': restart_attempted,
            'restart_events': restart_events,
        },
        'crawl_config': {
            'domains_count': len(domains),
            'domains': domains,
            'max_articles_per_site': max_articles_per_site,
            'concurrent_sites': concurrent_sites,
            'target_articles_approx': len(domains) * max_articles_per_site,
        },
        'job_result_summary': {
            'result_keys': sorted(list(job_result.keys())) if isinstance(job_result, dict) else [],
            'result_articles_count': len(job_result.get('articles', [])) if isinstance(job_result, dict) and isinstance(job_result.get('articles'), list) else None,
            'result_success': job_result.get('status') if isinstance(job_result, dict) else None,
            'result_message': job_result.get('message') if isinstance(job_result, dict) else None,
        },
        'baseline_metrics': baseline,
        'final_metrics': final,
        'deltas': {
            'articles_ingested_delta': ingested_delta,
            'synthesized_delta': synthesized_delta,
            'published_delta': published_delta,
            'living_story_updates': living_updates,
            'queue_total_delta': final['queue_total'] - baseline['queue_total'],
        },
        'efficiency': {
            'seconds_per_ingested_article': round(elapsed_sec / ingested_delta, 3) if ingested_delta > 0 else None,
            'ingested_articles_per_minute': round((ingested_delta / elapsed_sec) * 60.0, 3) if ingested_delta > 0 else 0.0,
            'seconds_per_synthesized_story': round(elapsed_sec / synthesized_delta, 3) if synthesized_delta > 0 else None,
            'seconds_per_published_story': round(elapsed_sec / published_delta, 3) if published_delta > 0 else None,
            'living_story_update_ratio_vs_ingested': round(living_updates / ingested_delta, 4) if ingested_delta > 0 else 0.0,
            'living_story_update_ratio_vs_synthesized': round(living_updates / synthesized_delta, 4) if synthesized_delta > 0 else 0.0,
        },
        'artifacts': {
            'samples_jsonl': str(sample_path),
            'report_json': str(report_path),
        },
    }

    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
