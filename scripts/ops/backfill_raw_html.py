#!/usr/bin/env python3
"""Re-extract and reingest raw html archives.

Usage:
    python scripts/ops/backfill_raw_html.py --dry-run
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import requests

SERVICE_DIR = Path(os.environ.get("SERVICE_DIR", Path(__file__).resolve().parents[2]))
RAW_DIR = Path(
    os.environ.get(
        "JUSTNEWS_RAW_HTML_DIR", SERVICE_DIR / "archive_storage" / "raw_html"
    )
)
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")


def _iter_raw_files(limit: int | None = None):
    if not RAW_DIR.exists():
        return
    files = sorted(RAW_DIR.glob("*.html"))
    for i, f in enumerate(files):
        if limit and i >= limit:
            return
        yield f


def backfill_file(path: Path, dry_run: bool = True):
    html = path.read_text(encoding="utf-8", errors="ignore")
    url = "unknown"
    payload = {
        "agent": "memory",
        "tool": "ingest_article",
        "args": [],
        "kwargs": {
            "article_payload": {
                "url": url,
                "content": html,
                "raw_html_ref": str(path.relative_to(SERVICE_DIR))
                if path.is_relative_to(SERVICE_DIR)
                else str(path),
            },
            "statements": [],
        },
    }

    if dry_run:
        print(f"Would POST to {MCP_BUS_URL}/call {path}")
        return True

    r = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=30)
    r.raise_for_status()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    count = 0
    for f in _iter_raw_files(limit=args.limit):
        try:
            backfill_file(f, dry_run=args.dry_run)
            count += 1
        except Exception as e:
            print(f"Failed to backfill {f}: {e}")
    print(f"Processed {count} files")


if __name__ == "__main__":
    main()
