#!/usr/bin/env python3
import json
import os
import time
import urllib.request
from datetime import datetime
from typing import Dict, Tuple

import mysql.connector
from dotenv import load_dotenv

load_dotenv('/app/global.env')

TARGET = int(os.getenv('CRAWL_TARGET_ARTICLES', '2000'))
POLL_SECONDS = int(os.getenv('CRAWL_POLL_SECONDS', '25'))
MIN_TRIGGER_INTERVAL = int(os.getenv('CRAWL_TRIGGER_INTERVAL', '45'))
COOLDOWN_SECONDS = int(os.getenv('CRAWL_BALANCER_COOLDOWN', '120'))

CPU_SCALE_UP_PERCENT = float(os.getenv('CRAWL_CPU_SCALE_UP_PERCENT', '65'))
CPU_THROTTLE_PERCENT = float(os.getenv('CRAWL_CPU_THROTTLE_PERCENT', '80'))
CPU_CRITICAL_PERCENT = float(os.getenv('CRAWL_CPU_CRITICAL_PERCENT', '90'))
LOW_TIER_MAX_RUNNING = int(os.getenv('CRAWL_LOW_TIER_MAX_RUNNING', '3'))
NORMAL_TIER_MAX_RUNNING = int(os.getenv('CRAWL_NORMAL_TIER_MAX_RUNNING', '2'))
LOW_TIER_CONCURRENT_SITES = int(os.getenv('CRAWL_LOW_TIER_CONCURRENT_SITES', '3'))
NORMAL_TIER_CONCURRENT_SITES = int(os.getenv('CRAWL_NORMAL_TIER_CONCURRENT_SITES', '2'))
HIGH_TIER_CONCURRENT_SITES = int(os.getenv('CRAWL_HIGH_TIER_CONCURRENT_SITES', '1'))
LOW_TIER_DOMAIN_BATCH = int(os.getenv('CRAWL_LOW_TIER_DOMAIN_BATCH', '24'))
NORMAL_TIER_DOMAIN_BATCH = int(os.getenv('CRAWL_NORMAL_TIER_DOMAIN_BATCH', '12'))
HIGH_TIER_DOMAIN_BATCH = int(os.getenv('CRAWL_HIGH_TIER_DOMAIN_BATCH', '6'))
ROUND_ROBIN_CURSOR_FILE = os.getenv('CRAWL_CURSOR_FILE', '/app/logs/crawl_round_robin_cursor.json')
INCLUDE_PAYWALL_SOURCES = os.getenv('CRAWL_INCLUDE_PAYWALL_SOURCES', 'false').lower() == 'true'
LOW_VALID_ARTICLE_THRESHOLD = int(os.getenv('CRAWL_LOW_VALID_ARTICLE_THRESHOLD', '2'))

NO_VALID_SKIP_STREAK = int(os.getenv('CRAWL_NO_VALID_SKIP_STREAK', '3'))
LOW_VALID_SKIP_STREAK = int(os.getenv('CRAWL_LOW_VALID_SKIP_STREAK', '4'))
MODAL_SKIP_THRESHOLD = int(os.getenv('CRAWL_MODAL_SKIP_THRESHOLD', '3'))
SKIP_COOLDOWN_HOURS = int(os.getenv('CRAWL_SKIP_COOLDOWN_HOURS', '12'))
MIN_RECRAWL_MINUTES = int(os.getenv('CRAWL_MIN_RECRAWL_MINUTES', '30'))

DEPTH = 4

crawler_port = os.getenv('CRAWLER_AGENT_PORT', '8022')
CRAWLER = f'http://127.0.0.1:{crawler_port}'
last_filter_stats: dict[str, int] = {}

BASE_KWARGS = {
    'max_sites': 60,
    'max_articles_per_site': 12,
    'strategy': 'unified',
    'enable_ai': False,
    'timeout': 2400,
    'depth': DEPTH,
    'crawl4ai': {'depth': DEPTH},
    'user_agent': 'JustNewsCrawler/safe-depth4-cpu-balanced-noai',
}


def get_json(url: str, timeout: int = 20) -> Dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def post_toolcall(url: str, kwargs_payload: Dict, timeout: int = 40) -> Tuple[int, Dict]:
    body = {'args': [], 'kwargs': kwargs_payload}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode('utf-8')
        return response.status, (json.loads(raw) if raw else {})


def stop_job(job_id: str) -> None:
    req = urllib.request.Request(f'{CRAWLER}/stop_job/{job_id}', data=b'', method='POST')
    with urllib.request.urlopen(req, timeout=20):
        return


def db_conn():
    return mysql.connector.connect(
        host=os.getenv('MARIADB_HOST', 'mariadb'),
        port=int(os.getenv('MARIADB_PORT', '3306')),
        user=os.getenv('MARIADB_USER', 'justnews'),
        password=os.getenv('MARIADB_PASSWORD', 'dev_justnews_password'),
        database=os.getenv('MARIADB_DB', 'justnews'),
    )


def db_articles() -> int:
    conn = db_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM articles')
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count


def load_cursor() -> int:
    try:
        with open(ROUND_ROBIN_CURSOR_FILE, 'r', encoding='utf-8') as file:
            payload = json.load(file)
        return int(payload.get('cursor', 0))
    except Exception:
        return 0


def save_cursor(cursor: int) -> None:
    os.makedirs(os.path.dirname(ROUND_ROBIN_CURSOR_FILE), exist_ok=True)
    with open(ROUND_ROBIN_CURSOR_FILE, 'w', encoding='utf-8') as file:
        json.dump({'cursor': int(cursor), 'updated_at': int(time.time())}, file)


def _load_json_metadata(raw_metadata) -> dict:
    if raw_metadata is None:
        return {}
    if isinstance(raw_metadata, dict):
        return dict(raw_metadata)
    if isinstance(raw_metadata, str):
        text = raw_metadata.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def fetch_source_domains() -> tuple[list[str], dict[str, int]]:
    conn = db_conn()
    cursor = conn.cursor()
    if INCLUDE_PAYWALL_SOURCES:
        cursor.execute(
            '''
            SELECT domain, COALESCE(paywall, 0), metadata
            FROM sources
            WHERE domain IS NOT NULL AND domain <> ''
            ORDER BY id ASC
            '''
        )
    else:
        cursor.execute(
            '''
            SELECT domain, COALESCE(paywall, 0), metadata
            FROM sources
            WHERE domain IS NOT NULL AND domain <> '' AND COALESCE(paywall, 0) = 0
            ORDER BY id ASC
            '''
        )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    now = datetime.utcnow()
    stats = {
        'total_rows': len(rows),
        'accepted': 0,
        'skip_paywall': 0,
        'skip_recent': 0,
        'skip_no_valid': 0,
        'skip_low_valid': 0,
        'skip_modal': 0,
    }

    domains: list[str] = []
    seen: set[str] = set()
    for domain_raw, paywall_flag, metadata_raw in rows:
        domain = (domain_raw or '').strip().lower()
        if '/' in domain:
            domain = domain.split('/', 1)[0].strip()
        if not domain or domain in seen:
            continue

        if int(paywall_flag) == 1 and not INCLUDE_PAYWALL_SOURCES:
            stats['skip_paywall'] += 1
            continue

        metadata = _load_json_metadata(metadata_raw)
        signals = metadata.get('crawl_signals') if isinstance(metadata.get('crawl_signals'), dict) else {}
        no_valid_streak = int(signals.get('no_valid_streak', 0) or 0)
        low_valid_streak = int(signals.get('low_valid_streak', 0) or 0)
        modal_hits_total = int(signals.get('modal_hits_total', 0) or 0)
        last_result_at = _parse_timestamp(signals.get('last_result_at'))

        if last_result_at is not None:
            elapsed_minutes = (now - last_result_at).total_seconds() / 60.0
            if elapsed_minutes < max(1, MIN_RECRAWL_MINUTES):
                stats['skip_recent'] += 1
                continue

            elapsed_hours = elapsed_minutes / 60.0
            if no_valid_streak >= max(1, NO_VALID_SKIP_STREAK) and elapsed_hours < max(1, SKIP_COOLDOWN_HOURS):
                stats['skip_no_valid'] += 1
                continue
            if low_valid_streak >= max(1, LOW_VALID_SKIP_STREAK) and elapsed_hours < max(1, SKIP_COOLDOWN_HOURS):
                stats['skip_low_valid'] += 1
                continue
            if modal_hits_total >= max(1, MODAL_SKIP_THRESHOLD) and elapsed_hours < max(1, SKIP_COOLDOWN_HOURS):
                stats['skip_modal'] += 1
                continue

        seen.add(domain)
        domains.append(domain)
        stats['accepted'] += 1

    return domains, stats


def next_domain_batch(limit: int) -> list[str]:
    global last_filter_stats

    domains, stats = fetch_source_domains()
    last_filter_stats = stats
    if not domains:
        return []

    batch_size = max(1, min(limit, len(domains)))
    cursor = load_cursor() % len(domains)
    batch = [domains[(cursor + offset) % len(domains)] for offset in range(batch_size)]
    save_cursor((cursor + batch_size) % len(domains))
    return batch


def update_source_metadata_from_job(job_id: str, result: dict) -> None:
    site_breakdown = result.get('site_breakdown') or {}
    site_attempted = result.get('site_attempted_breakdown') or {}
    site_exhaustion = result.get('site_exhaustion') or {}
    site_paywalls = result.get('site_paywall_breakdown') or {}

    if not isinstance(site_breakdown, dict):
        site_breakdown = {}
    if not isinstance(site_attempted, dict):
        site_attempted = {}
    if not isinstance(site_exhaustion, dict):
        site_exhaustion = {}
    if not isinstance(site_paywalls, dict):
        site_paywalls = {}

    domains = set(site_breakdown.keys()) | set(site_attempted.keys()) | set(site_exhaustion.keys()) | set(site_paywalls.keys())
    if not domains:
        return

    conn = db_conn()
    cursor = conn.cursor()
    now_ts = time.strftime('%Y-%m-%d %H:%M:%S')
    for domain_raw in domains:
        domain = (domain_raw or '').strip().lower()
        attempted = int(site_attempted.get(domain, site_breakdown.get(domain, 0)) or 0)
        ingested = int(site_breakdown.get(domain, 0) or 0)
        paywall_hits = int(site_paywalls.get(domain, 0) or 0)
        exhaustion_reason = str(site_exhaustion.get(domain, '') or '')
        exhaustion_lower = exhaustion_reason.lower()
        modal_detected = ('modal' in exhaustion_lower) or ('consent' in exhaustion_lower)

        cursor.execute('SELECT id, metadata, COALESCE(paywall, 0) FROM sources WHERE domain = %s LIMIT 1', (domain,))
        source_row = cursor.fetchone()
        if not source_row:
            continue

        source_id, metadata_raw, paywall_flag = source_row
        metadata = _load_json_metadata(metadata_raw)
        crawl_meta = metadata.get('crawl_signals') if isinstance(metadata.get('crawl_signals'), dict) else {}

        previous_no_valid = int(crawl_meta.get('no_valid_streak', 0) or 0)
        previous_low_valid = int(crawl_meta.get('low_valid_streak', 0) or 0)
        previous_paywall_hits = int(crawl_meta.get('paywall_hits_total', 0) or 0)
        previous_modal_hits = int(crawl_meta.get('modal_hits_total', 0) or 0)

        no_valid_streak = previous_no_valid + 1 if attempted == 0 else 0
        low_valid_streak = previous_low_valid + 1 if 0 < attempted < LOW_VALID_ARTICLE_THRESHOLD else 0

        crawl_meta.update(
            {
                'last_job_id': job_id,
                'last_result_at': now_ts,
                'last_attempted': attempted,
                'last_ingested': ingested,
                'last_exhaustion': exhaustion_reason,
                'no_valid_streak': no_valid_streak,
                'low_valid_streak': low_valid_streak,
                'paywall_hits_total': previous_paywall_hits + paywall_hits,
                'modal_hits_total': previous_modal_hits + (1 if modal_detected else 0),
            }
        )
        metadata['crawl_signals'] = crawl_meta

        new_paywall = 1 if (int(paywall_flag) == 1 or paywall_hits > 0) else int(paywall_flag)
        cursor.execute(
            'UPDATE sources SET metadata = %s, paywall = %s, last_crawl_at = NOW() WHERE id = %s',
            (json.dumps(metadata, ensure_ascii=False), new_paywall, source_id),
        )

    conn.commit()
    cursor.close()
    conn.close()


def read_cpu_times() -> Tuple[int, int]:
    with open('/proc/stat', 'r', encoding='utf-8') as file:
        first = file.readline().strip().split()
    values = [int(value) for value in first[1:]]
    idle = values[3] + values[4]
    total = sum(values)
    return total, idle


def cpu_utilization_percent(prev_times: Tuple[int, int]) -> Tuple[float, Tuple[int, int]]:
    current_total, current_idle = read_cpu_times()
    previous_total, previous_idle = prev_times
    total_delta = current_total - previous_total
    idle_delta = current_idle - previous_idle

    if total_delta <= 0:
        return 0.0, (current_total, current_idle)

    busy_delta = total_delta - idle_delta
    utilization = (busy_delta / total_delta) * 100.0
    return utilization, (current_total, current_idle)


def policy(cpu_percent: float) -> Tuple[str, int, int, int, bool]:
    if cpu_percent >= CPU_CRITICAL_PERCENT:
        return ('critical', 0, HIGH_TIER_CONCURRENT_SITES, HIGH_TIER_DOMAIN_BATCH, True)
    if cpu_percent >= CPU_THROTTLE_PERCENT:
        return ('high', 1, HIGH_TIER_CONCURRENT_SITES, HIGH_TIER_DOMAIN_BATCH, False)
    if cpu_percent <= CPU_SCALE_UP_PERCENT:
        return ('low', LOW_TIER_MAX_RUNNING, LOW_TIER_CONCURRENT_SITES, LOW_TIER_DOMAIN_BATCH, False)
    return ('normal', NORMAL_TIER_MAX_RUNNING, NORMAL_TIER_CONCURRENT_SITES, NORMAL_TIER_DOMAIN_BATCH, False)


print('CPU_BALANCED_DEPTH4_MONITOR_START')
print(
    f'config depth={DEPTH} target={TARGET} '
    f'cpu_scale_up={CPU_SCALE_UP_PERCENT}% cpu_throttle={CPU_THROTTLE_PERCENT}% '
    f'cpu_critical={CPU_CRITICAL_PERCENT}% low_tier_cap={LOW_TIER_MAX_RUNNING} '
    f'concurrent_sites(low/normal/high)={LOW_TIER_CONCURRENT_SITES}/'
    f'{NORMAL_TIER_CONCURRENT_SITES}/{HIGH_TIER_CONCURRENT_SITES} '
    f'domain_batch(low/normal/high)={LOW_TIER_DOMAIN_BATCH}/'
    f'{NORMAL_TIER_DOMAIN_BATCH}/{HIGH_TIER_DOMAIN_BATCH} include_paywalls={INCLUDE_PAYWALL_SOURCES} '
    f'min_recrawl_min={MIN_RECRAWL_MINUTES} cooldown_h={SKIP_COOLDOWN_HOURS}'
)

start_articles = db_articles()
print(f'initial_articles={start_articles}')

last_trigger_ts = 0.0
last_scale_ts = 0.0
previous_cpu_times = read_cpu_times()
processed_terminal_jobs: set[str] = set()

while True:
    now = time.time()
    articles = db_articles()
    jobs = get_json(f'{CRAWLER}/jobs')

    running = [jid for jid, status in jobs.items() if str(status).lower() == 'running']
    pending = [jid for jid, status in jobs.items() if str(status).lower() == 'pending']

    cpu_percent, previous_cpu_times = cpu_utilization_percent(previous_cpu_times)
    tier, desired_running, concurrent_sites, domain_batch, stop_excess = policy(cpu_percent)

    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
        f"articles={articles} delta={articles - start_articles} "
        f"running={len(running)} pending={len(pending)} cpu={cpu_percent:.1f}% tier={tier}"
    )

    if articles >= TARGET:
        print('TARGET_REACHED_2K')
        break

    if stop_excess and len(running) > desired_running and (now - last_scale_ts) >= COOLDOWN_SECONDS:
        to_stop = running[desired_running:]
        for job_id in to_stop:
            try:
                stop_job(job_id)
                print(f'THROTTLE_STOP job_id={job_id} reason=critical_load')
            except Exception as exc:
                print(f'THROTTLE_STOP_ERROR job_id={job_id} error={exc}')
        last_scale_ts = now

    for job_id, status in jobs.items():
        normalized = str(status).lower()
        if normalized not in {'completed', 'failed', 'cancelled'}:
            continue
        if job_id in processed_terminal_jobs:
            continue

        try:
            job_details = get_json(f'{CRAWLER}/job_status/{job_id}')
            result = job_details.get('result')
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except Exception:
                    result = {}
            if isinstance(result, dict):
                update_source_metadata_from_job(job_id, result)
                print(f'METADATA_UPDATED job_id={job_id} status={normalized}')
        except Exception as exc:
            print(f'METADATA_UPDATE_ERROR job_id={job_id} error={exc}')
        finally:
            processed_terminal_jobs.add(job_id)

    if (
        len(running) < desired_running
        and (now - last_trigger_ts) >= MIN_TRIGGER_INTERVAL
    ):
        domains = next_domain_batch(domain_batch)
        if not domains:
            print(f'TRIGGER_SKIP reason=no_domains filter_stats={last_filter_stats}')
            time.sleep(POLL_SECONDS)
            continue

        kwargs_payload = dict(BASE_KWARGS)
        kwargs_payload['concurrent_sites'] = concurrent_sites
        kwargs_payload['domains'] = domains
        try:
            status, data = post_toolcall(f'{CRAWLER}/unified_production_crawl', kwargs_payload)
            print(
                f"TRIGGER status={status} job_id={data.get('job_id')} depth={DEPTH} "
                f"concurrent_sites={concurrent_sites} domains={len(domains)} tier={tier} "
                f"filter_stats={last_filter_stats}"
            )
            last_trigger_ts = now
            last_scale_ts = now
        except Exception as exc:
            print(f'TRIGGER_ERROR error={exc} tier={tier}')

    time.sleep(POLL_SECONDS)

final_articles = db_articles()
print(f'CPU_BALANCED_DEPTH4_MONITOR_DONE final_articles={final_articles} total_delta={final_articles - start_articles}')
