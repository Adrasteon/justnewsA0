#!/usr/bin/env python3
"""Validate lane and accounting contracts for unified crawler summaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('summary payload must be a JSON object')
    return payload


def _validate(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    lane2 = payload.get('lane2_fallback')
    if not isinstance(lane2, dict):
        errors.append('missing lane2_fallback object')
    else:
        for key in ('enabled', 'triggered', 'attempted_sites', 'ingested', 'attempted_domains'):
            if key not in lane2:
                errors.append(f'lane2_fallback missing key: {key}')

    preflight = payload.get('preflight')
    if not isinstance(preflight, dict):
        errors.append('missing preflight object')

    site_breakdown = payload.get('site_breakdown')
    site_details = payload.get('site_ingestion_details')
    if not isinstance(site_breakdown, dict):
        errors.append('missing site_breakdown object')
    if not isinstance(site_details, dict):
        errors.append('missing site_ingestion_details object')

    if isinstance(site_breakdown, dict) and isinstance(site_details, dict):
        for domain in site_breakdown:
            details = site_details.get(domain)
            if not isinstance(details, list) or not details:
                errors.append(f'site_ingestion_details missing non-empty details for {domain}')

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate crawler lane behavior contract')
    parser.add_argument('summary_json', help='Path to crawler summary JSON file')
    args = parser.parse_args()

    payload = _load_payload(Path(args.summary_json))
    errors = _validate(payload)
    if errors:
        for err in errors:
            print(f'ERROR: {err}')
        return 1

    print('OK: crawler summary satisfies lane/preflight/detail contracts')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
