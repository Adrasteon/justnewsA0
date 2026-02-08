#!/usr/bin/env python3
"""Lightweight editorial pipeline for canary end-to-end testing.

This script reads parsed outputs from `output/canary_parsed/*.json`, runs a
small set of heuristic checks (fact-check simulation, minimum quality checks)
and emits draft JSONs into `output/canary_drafts/` representing a ready-for-review
article draft. This avoids depending on heavy LLM models during smoke runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.dev.canary_metrics import incr

PARSED_DIR = Path.cwd() / "output" / "canary_parsed"
OUT_DIR = Path.cwd() / "output" / "canary_drafts"


def find_parsed_files() -> list[Path]:
    return sorted(PARSED_DIR.glob("*.json")) if PARSED_DIR.exists() else []


def simple_fact_check(text: str) -> dict:
    # Basic heuristics as placeholders for real fact checks
    issues = []
    if not text or len(text.split()) < 20:
        issues.append("too_short")
    if "lorem ipsum" in text.lower():
        issues.append("placeholder_text")
    return {"issues": issues, "confidence": 0.9 if not issues else 0.2}


def create_draft(parsed_path: Path) -> Path:
    payload = json.loads(parsed_path.read_text(encoding="utf-8"))
    title = payload.get("title") or "Untitled"
    text = payload.get("text") or ""

    fact = simple_fact_check(text)
    draft = {
        "url": payload.get("url"),
        "title": title,
        "summary": text[:300].strip(),
        "word_count": payload.get("word_count"),
        "fact_check": fact,
        "ready_for_review": fact["confidence"] >= 0.5
        and payload.get("word_count", 0) >= 50,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / parsed_path.name
    out_path.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    incr("draft_created")
    return out_path


def main() -> list[str]:
    files = find_parsed_files()
    return [str(create_draft(p)) for p in files]


if __name__ == "__main__":
    for p in main():
        print(p)
