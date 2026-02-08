#!/usr/bin/env python3
"""Basic documentation policy enforcement for CI lint runs."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"


def main() -> int:
    """Verify that the docs directory exists and contains Markdown files."""
    if not DOCS_DIR.exists():
        print("[docs-policy] Missing docs/ directory", file=sys.stderr)
        return 1

    markdown_files = list(DOCS_DIR.rglob("*.md"))
    if not markdown_files:
        print("[docs-policy] No Markdown files found under docs/", file=sys.stderr)
        return 1

    print(
        f"[docs-policy] docs/ contains {len(markdown_files)} Markdown file(s); policy satisfied."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
