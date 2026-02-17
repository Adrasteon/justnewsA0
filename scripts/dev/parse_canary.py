#!/usr/bin/env python3
"""Run the extraction pipeline against canary raw files and emit parsed JSONs.

Uses agents.crawler.extraction.extract_article_content to produce a structured
ExtractionOutcome; writes results to `output/canary_parsed/`.
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.crawler.extraction import extract_article_content
from scripts.dev.canary_metrics import incr

RAW_DIR = Path.cwd() / "output" / "canary_raw"
OUT_DIR = Path.cwd() / "output" / "canary_parsed"


def find_raw_files() -> list[Path]:
    return sorted(RAW_DIR.glob("*.json")) if RAW_DIR.exists() else []


def parse_file(path: Path) -> Path:
    data = json.loads(path.read_text(encoding="utf-8"))
    html = data.get("html", "")
    url = data.get("url", "")
    outcome = extract_article_content(html, url)
    out = {
        "url": url,
        "title": outcome.title,
        "text": outcome.text,
        "word_count": outcome.word_count,
        "canonical_url": outcome.canonical_url,
        "extraction_used": outcome.extractor_used,
        "needs_review": outcome.needs_review,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / path.name
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    incr("parse_success")
    return out_path


def main():
    files = find_raw_files()
    return [str(parse_file(p)) for p in files]


if __name__ == "__main__":
    items = main()
    for i in items:
        print(i)
