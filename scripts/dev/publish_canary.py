#!/usr/bin/env python3
"""Simple publisher for canary smoke tests.

Reads draft JSON files from `output/canary_drafts/` and writes a published JSON
to `output/canary_published/` including the final public URL (simulated).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.dev.canary_metrics import incr

DRAFT_DIR = Path.cwd() / "output" / "canary_drafts"
OUT_DIR = Path.cwd() / "output" / "canary_published"


def find_drafts() -> list[Path]:
    return sorted(DRAFT_DIR.glob("*.json")) if DRAFT_DIR.exists() else []


def publish_draft(path: Path) -> Path:
    draft = json.loads(path.read_text(encoding="utf-8"))
    title = draft.get("title") or "untitled"
    slug = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
    public_url = f"http://localhost:8013/articles/{slug}"
    out = {
        "url": draft.get("url"),
        "title": title,
        "summary": draft.get("summary"),
        "published_url": public_url,
        "published_at": draft.get("published_at") or None,
        "is_published": True,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{slug}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    incr("publish_success")
    return out_path


def main() -> list[str]:
    items = []
    for p in find_drafts():
        items.append(str(publish_draft(p)))
    return items


if __name__ == "__main__":
    for p in main():
        print(p)
