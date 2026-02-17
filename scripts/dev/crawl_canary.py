#!/usr/bin/env python3
"""Small canary fetcher for local tests.

Reads `scripts/dev/canary_urls.txt`, fetches each URL and writes a JSON record
to `output/canary_raw/` with fields: url, status_code, headers, html (truncated).

Designed for smoke testing only (non-production).
"""

import hashlib
import json
from pathlib import Path

import requests

from scripts.dev.canary_metrics import incr

CANARY_FILE = Path(__file__).parent / "canary_urls.txt"
OUT_DIR = Path.cwd() / "output" / "canary_raw"


def read_canary_urls() -> list[str]:
    text = CANARY_FILE.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def fetch_and_store(url: str) -> Path:
    r = requests.get(url, timeout=20)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    out_path = OUT_DIR / f"{key}.json"
    record = {
        "url": url,
        "status_code": r.status_code,
        "headers": dict(r.headers),
        # keep only first 50k chars of HTML for smoke storage
        "html": r.text[:50000],
    }
    out_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    incr("fetch_success")
    return out_path


def main():
    urls = read_canary_urls()
    res = []
    for u in urls:
        try:
            p = fetch_and_store(u)
            res.append((u, True, str(p)))
        except Exception as e:
            res.append((u, False, str(e)))
    return res


if __name__ == "__main__":
    out = main()
    for u, ok, meta in out:
        status = "OK" if ok else "ERR"
        print(f"[{status}] {u} -> {meta}")
