#!/usr/bin/env python3
"""Report indexer health, daemon status, and token savings trend."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from statistics import mean
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Show token reduction trend plus index/daemon health status',
    )
    parser.add_argument(
        '--telemetry-path',
        default='run/indexing_telemetry.jsonl',
        help='Telemetry JSONL file path',
    )
    parser.add_argument(
        '--index-dir',
        default='.cache/code_index',
        help='Index directory path',
    )
    parser.add_argument(
        '--daemon-script',
        default='scripts/indexing/index_autoupdate_daemon.sh',
        help='Daemon control script path',
    )
    parser.add_argument(
        '--recent-window',
        type=int,
        default=5,
        help='Window size used to evaluate recent token trend',
    )
    parser.add_argument(
        '--healthy-max-age-hours',
        type=float,
        default=24.0,
        help='Max age of latest build event for healthy status',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Print JSON only',
    )
    return parser.parse_args()


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except Exception:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    return events


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _daemon_status(daemon_script: Path) -> tuple[bool, str]:
    if not daemon_script.exists():
        return False, 'daemon script missing'
    try:
        proc = subprocess.run(
            ['bash', str(daemon_script), 'status'],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return False, f'daemon status error: {exc}'

    output = (proc.stdout or proc.stderr or '').strip()
    active = 'daemon running' in output
    return active, output


def _token_rows(query_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in query_events:
        pct_raw = event.get('token_savings_pct', event.get('estimated_token_savings_pct'))
        saved_raw = event.get('token_savings', event.get('estimated_token_savings'))
        base_raw = event.get('baseline_snippet_tokens', event.get('baseline_snippet_tokens_estimate'))
        idx_raw = event.get('indexed_snippet_tokens', event.get('indexed_snippet_tokens_estimate'))

        base = _safe_float(base_raw)
        idx = _safe_float(idx_raw)
        pct = _safe_float(pct_raw) if pct_raw is not None else None
        saved = _safe_float(saved_raw) if saved_raw is not None else None

        if pct is None and base > 0.0:
            pct = ((base - idx) / base) * 100.0
        if saved is None and base > 0.0:
            saved = base - idx

        if pct is None:
            continue

        rows.append(
            {
                'ts_iso': str(event.get('ts_iso') or ''),
                'query': str(event.get('query') or ''),
                'pct': float(pct),
                'saved': float(saved or 0.0),
                'base': float(base),
                'idx': float(idx),
            }
        )
    return rows


def _trend_label(delta_pct: float) -> str:
    if delta_pct > 1.0:
        return 'improving'
    if delta_pct < -1.0:
        return 'declining'
    return 'stable'


def main() -> int:
    args = parse_args()

    telemetry_path = Path(args.telemetry_path)
    index_dir = Path(args.index_dir)
    daemon_script = Path(args.daemon_script)
    now = time.time()

    events = _load_events(telemetry_path)
    query_events = [event for event in events if event.get('event_type') == 'index_query']
    build_events = [event for event in events if event.get('event_type') == 'index_build']
    autoupdate_events = [event for event in events if event.get('event_type') == 'index_autoupdate']

    token_rows = _token_rows(query_events)
    window = max(int(args.recent_window), 1)
    recent = token_rows[-window:]
    previous = token_rows[-(window * 2) : -window] if len(token_rows) > window else []

    avg_recent = mean([row['pct'] for row in recent]) if recent else 0.0
    avg_previous = mean([row['pct'] for row in previous]) if previous else avg_recent
    delta_recent_vs_previous = avg_recent - avg_previous
    avg_all = mean([row['pct'] for row in token_rows]) if token_rows else 0.0

    latest_build = build_events[-1] if build_events else {}
    latest_build_ts_epoch = _safe_float(latest_build.get('ts_epoch'))
    latest_build_age_hours = (now - latest_build_ts_epoch) / 3600.0 if latest_build_ts_epoch > 0 else 0.0
    latest_build_recent_enough = (
        latest_build_ts_epoch > 0
        and latest_build_age_hours <= float(args.healthy_max_age_hours)
    )
    latest_build_files_indexed = _safe_int(latest_build.get('files_indexed'))
    latest_build_entries_total = _safe_int(latest_build.get('entries_total'))

    latest_autoupdate = autoupdate_events[-1] if autoupdate_events else {}
    latest_autoupdate_exit = _safe_int(latest_autoupdate.get('exit_code'))
    autoupdate_ok = bool(autoupdate_events) and latest_autoupdate_exit == 0

    manifest_path = index_dir / 'manifest.json'
    entries_path = index_dir / 'entries.jsonl'
    manifest_exists = manifest_path.exists()
    entries_exists = entries_path.exists()

    daemon_active, daemon_status_text = _daemon_status(daemon_script)

    index_healthy = all(
        [
            manifest_exists,
            entries_exists,
            latest_build_files_indexed > 0,
            latest_build_entries_total > 0,
            latest_build_recent_enough,
            autoupdate_ok,
        ]
    )

    token_reduction_active = bool(token_rows) and avg_recent > 0.0
    trend = _trend_label(delta_recent_vs_previous)

    payload = {
        'daemon_active': daemon_active,
        'daemon_status_text': daemon_status_text,
        'index_healthy': index_healthy,
        'index_checks': {
            'manifest_exists': manifest_exists,
            'entries_exists': entries_exists,
            'latest_build_files_indexed': latest_build_files_indexed,
            'latest_build_entries_total': latest_build_entries_total,
            'latest_build_ts_iso': str(latest_build.get('ts_iso') or ''),
            'latest_build_age_hours': round(latest_build_age_hours, 3),
            'latest_build_recent_enough': latest_build_recent_enough,
            'latest_autoupdate_ts_iso': str(latest_autoupdate.get('ts_iso') or ''),
            'latest_autoupdate_exit_code': latest_autoupdate_exit,
            'latest_autoupdate_ok': autoupdate_ok,
        },
        'token_reduction_active': token_reduction_active,
        'token_trend': trend,
        'token_stats': {
            'token_query_events': len(token_rows),
            'avg_savings_pct_all': round(avg_all, 3),
            'avg_savings_pct_recent_window': round(avg_recent, 3),
            'avg_savings_pct_previous_window': round(avg_previous, 3),
            'delta_recent_vs_previous_pct_points': round(delta_recent_vs_previous, 3),
            'window_size': window,
            'latest_event': token_rows[-1] if token_rows else {},
        },
        'telemetry_path': telemetry_path.as_posix(),
        'index_dir': index_dir.as_posix(),
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    print('INDEXER STATUS REPORT')
    print(f"DAEMON_ACTIVE: {'YES' if payload['daemon_active'] else 'NO'}")
    print(f"INDEX_HEALTHY: {'YES' if payload['index_healthy'] else 'NO'}")
    print(
        f"TOKEN_REDUCTION_ACTIVE: {'YES' if payload['token_reduction_active'] else 'NO'} "
        f"(avg recent savings {payload['token_stats']['avg_savings_pct_recent_window']:.3f}%)"
    )
    print(
        f"TOKEN_TREND: {payload['token_trend'].upper()} "
        f"(delta {payload['token_stats']['delta_recent_vs_previous_pct_points']:+.3f} pp)"
    )
    print(f"TELEMETRY_EVENTS_WITH_TOKEN_STATS: {payload['token_stats']['token_query_events']}")
    print('---')
    print(f"daemon: {payload['daemon_status_text']}")
    print(
        'latest_build: '
        f"{payload['index_checks']['latest_build_ts_iso']} "
        f"(age_hours={payload['index_checks']['latest_build_age_hours']:.3f}, "
        f"files={payload['index_checks']['latest_build_files_indexed']}, "
        f"entries={payload['index_checks']['latest_build_entries_total']})"
    )
    print(
        'latest_autoupdate: '
        f"{payload['index_checks']['latest_autoupdate_ts_iso']} "
        f"(exit_code={payload['index_checks']['latest_autoupdate_exit_code']})"
    )
    latest_event = payload['token_stats']['latest_event']
    if latest_event:
        print(
            'latest_token_event: '
            f"{latest_event.get('ts_iso', '')} "
            f"(pct={latest_event.get('pct', 0.0):.3f}, "
            f"saved={int(latest_event.get('saved', 0.0))}) "
            f"query={latest_event.get('query', '')}"
        )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())