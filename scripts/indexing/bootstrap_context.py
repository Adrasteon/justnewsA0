#!/usr/bin/env python3
"""Collect index and memory context for a fresh chat bootstrap."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Bootstrap local index context for new chats')
    parser.add_argument('--root', default='.', help='Repository root')
    parser.add_argument('--index-dir', default='.cache/code_index', help='Index artifact directory')
    parser.add_argument('--telemetry-path', default='run/indexing_telemetry.jsonl', help='Telemetry JSONL path')
    parser.add_argument('--json', action='store_true', help='Emit JSON summary')
    parser.add_argument('--telemetry-sample', type=int, default=200, help='Last N telemetry events to inspect')
    return parser.parse_args()


def _iso_from_epoch(value: float | int | None) -> str:
    if not value:
        return ''
    try:
        return datetime.fromtimestamp(float(value), tz=UTC).isoformat().replace('+00:00', 'Z')
    except Exception:
        return ''


def _file_info(path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        'path': path.as_posix(),
        'exists': path.exists(),
    }
    if not path.exists():
        return info
    try:
        stat = path.stat()
        info['size_bytes'] = int(stat.st_size)
        info['mtime_epoch'] = float(stat.st_mtime)
        info['mtime_iso'] = _iso_from_epoch(stat.st_mtime)
    except Exception:
        pass
    return info


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _tail_jsonl(path: Path, last_n: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except Exception:
        return []

    selected = lines[-max(int(last_n), 1) :]
    events: list[dict[str, Any]] = []
    for line in selected:
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


def _daemon_status(root: Path) -> dict[str, Any]:
    pid_file = root / 'run' / 'code-index-autoupdate.pid'
    status: dict[str, Any] = {
        'pid_file': pid_file.as_posix(),
        'pid_file_exists': pid_file.exists(),
        'running': False,
        'pid': None,
    }
    if not pid_file.exists():
        return status

    try:
        pid_text = pid_file.read_text(encoding='utf-8').strip()
        pid = int(pid_text)
        status['pid'] = pid
    except Exception:
        return status

    if os.path.exists(f'/proc/{pid}'):
        status['running'] = True
    return status


def _chat_model_binding_status(root: Path) -> dict[str, Any]:
    binding_path = root / 'run' / 'copilot_chat_model.env'
    status: dict[str, Any] = {
        'path': binding_path.as_posix(),
        'exists': binding_path.exists(),
        'model': '',
        'source': '',
    }
    if not binding_path.exists():
        return status

    try:
        lines = binding_path.read_text(encoding='utf-8').splitlines()
    except Exception:
        return status

    for line in lines:
        text = line.strip()
        if not text or text.startswith('#') or '=' not in text:
            continue
        key, value = text.split('=', 1)
        k = key.strip()
        v = value.strip().strip('"').strip("'")
        if k == 'COPILOT_CHAT_MODEL':
            status['model'] = v
        elif k == 'COPILOT_CHAT_MODEL_SOURCE':
            status['source'] = v
    return status


def _build_summary(root: Path, index_dir: Path, telemetry_path: Path, telemetry_sample: int) -> dict[str, Any]:
    manifest_path = index_dir / 'manifest.json'
    entries_path = index_dir / 'entries.jsonl'

    manifest = _load_manifest(manifest_path)
    telemetry_events = _tail_jsonl(telemetry_path, last_n=telemetry_sample)
    event_types = Counter(str(item.get('event_type') or 'unknown') for item in telemetry_events)

    memory_paths = [
        Path('/memories/repo/operations_notes.md'),
        Path('/memories/repo/query_pitfalls.md'),
    ]
    memories_root = Path('/memories')
    memory_visible = memories_root.exists()
    doc_paths = [
        root / 'scripts' / 'indexing' / 'README.md',
        root / 'docs' / 'developer' / 'CODE_INDEX_MEMORY_PLAYBOOK.md',
        root / 'Makefile',
    ]

    files_section = {
        'manifest': _file_info(manifest_path),
        'entries': _file_info(entries_path),
        'telemetry': _file_info(telemetry_path),
    }

    if manifest:
        files_section['manifest']['files_indexed'] = int(manifest.get('files_indexed') or 0)
        files_section['manifest']['entries_total'] = int(manifest.get('entries_total') or 0)
        files_section['manifest']['index_version'] = int(manifest.get('index_version') or 0)

    last_event_ts = ''
    if telemetry_events:
        last = telemetry_events[-1]
        last_event_ts = str(last.get('ts_iso') or '')

    return {
        'generated_at_epoch': time.time(),
        'generated_at_iso': datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        'root': root.as_posix(),
        'index_dir': index_dir.as_posix(),
        'files': files_section,
        'telemetry': {
            'sampled_events': len(telemetry_events),
            'event_breakdown': dict(event_types),
            'last_event_ts': last_event_ts,
        },
        'daemon_fallback': _daemon_status(root),
        'chat_model_binding': _chat_model_binding_status(root),
        'memory_visibility': 'mounted' if memory_visible else 'not-mounted-in-shell',
        'memory_files': [
            _file_info(path)
            if memory_visible
            else {
                'path': path.as_posix(),
                'exists': None,
                'note': 'Memory store is available via memory tool, not shell filesystem',
            }
            for path in memory_paths
        ],
        'read_first': [_file_info(path) for path in doc_paths],
        'recommended_commands': [
            'make index-build',
            "make index-query QUERY='your topic here'",
            'make index-telemetry-summary',
            'make index-auto-status',
        ],
    }


def _print_human(summary: dict[str, Any]) -> None:
    print('New-Chat Bootstrap')
    print('==================')
    print(f"Generated: {summary.get('generated_at_iso', '')}")
    print(f"Root: {summary.get('root', '')}")
    print('')

    files = summary.get('files', {})
    manifest = files.get('manifest', {}) if isinstance(files, dict) else {}
    entries = files.get('entries', {}) if isinstance(files, dict) else {}
    telemetry = files.get('telemetry', {}) if isinstance(files, dict) else {}

    print('Index Artifacts')
    print(f"- Manifest exists: {manifest.get('exists', False)}")
    if manifest.get('exists', False):
        print(f"- Files indexed: {manifest.get('files_indexed', 0)}")
        print(f"- Entries total: {manifest.get('entries_total', 0)}")
        print(f"- Manifest updated: {manifest.get('mtime_iso', '')}")
    print(f"- Entries exists: {entries.get('exists', False)}")
    print(f"- Telemetry file exists: {telemetry.get('exists', False)}")
    if telemetry.get('exists', False):
        print(f"- Telemetry updated: {telemetry.get('mtime_iso', '')}")
    print('')

    telemetry_section = summary.get('telemetry', {})
    event_breakdown = telemetry_section.get('event_breakdown', {})
    print('Telemetry Snapshot')
    print(f"- Sampled events: {telemetry_section.get('sampled_events', 0)}")
    print(f"- Last event: {telemetry_section.get('last_event_ts', '')}")
    print(f"- Event breakdown: {json.dumps(event_breakdown, ensure_ascii=True)}")
    print('')

    daemon = summary.get('daemon_fallback', {})
    print('Autoupdate Daemon Fallback')
    print(f"- PID file exists: {daemon.get('pid_file_exists', False)}")
    print(f"- Running: {daemon.get('running', False)}")
    print('')

    chat_binding = summary.get('chat_model_binding', {})
    print('Chat Model Binding')
    print(f"- Binding file exists: {chat_binding.get('exists', False)}")
    print(f"- Model: {chat_binding.get('model', '')}")
    print(f"- Source: {chat_binding.get('source', '')}")
    print('')

    print('Read First')
    for item in summary.get('read_first', []):
        path = str(item.get('path', ''))
        exists = bool(item.get('exists', False))
        print(f"- {path} (exists={exists})")
    print('')

    print('Memory Files')
    print(f"- Visibility: {summary.get('memory_visibility', 'unknown')}")
    for item in summary.get('memory_files', []):
        path = str(item.get('path', ''))
        exists = item.get('exists', False)
        if exists is None:
            print(f"- {path} (exists=unknown, note={item.get('note', '')})")
            continue
        print(f"- {path} (exists={bool(exists)})")
    print('')

    print('Recommended Commands')
    for command in summary.get('recommended_commands', []):
        print(f'- {command}')


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    index_dir = (root / args.index_dir).resolve()
    telemetry_path = (root / args.telemetry_path).resolve()

    summary = _build_summary(root, index_dir, telemetry_path, telemetry_sample=int(args.telemetry_sample))

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=True))
    else:
        _print_human(summary)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
