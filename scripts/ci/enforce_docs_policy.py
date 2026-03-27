#!/usr/bin/env python3
"""Documentation policy enforcement for CI lint runs."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = REPO_ROOT / "docs"
DOC_INDEX = DOCS_DIR / "DOCUMENTATION_INDEX.md"


def _slugify_heading(heading: str) -> str:
    h = heading.strip().lower()
    h = re.sub(r"[\u2000-\u206F\u2E00-\u2E7F\\!\"#$%&'()*+,./:;<=>?@\[\]^`{|}~]", "", h)
    h = re.sub(r"\s+", "-", h).strip("-")
    h = re.sub(r"-+", "-", h)
    return h


def _collect_headings(path: Path) -> set[str]:
    if not path.exists() or not path.is_file():
        return set()

    slugs: list[str] = []
    counts: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = re.match(r"\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue

        base = _slugify_heading(match.group(2))
        if not base:
            continue

        idx = counts.get(base, 0)
        slug = base if idx == 0 else f"{base}-{idx}"
        counts[base] = idx + 1
        slugs.append(slug)

    return set(slugs)


def _validate_doc_index() -> list[str]:
    errors: list[str] = []

    if not DOC_INDEX.exists():
        errors.append("docs/DOCUMENTATION_INDEX.md missing")
        return errors

    text = DOC_INDEX.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 1) Balanced fenced code blocks
    fence_count = sum(1 for line in lines if line.strip().startswith("```"))
    if fence_count % 2 != 0:
        errors.append(
            f"docs/DOCUMENTATION_INDEX.md has unbalanced fenced code blocks (count={fence_count})"
        )

    # 2) Validate local markdown links + anchors
    heading_cache: dict[Path, set[str]] = {}

    def headings_for(path: Path) -> set[str]:
        if path not in heading_cache:
            heading_cache[path] = _collect_headings(path)
        return heading_cache[path]

    link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")

    for i, line in enumerate(lines, start=1):
        for match in link_re.finditer(line):
            raw = match.group(1).strip()
            if raw.startswith(("http://", "https://", "mailto:")):
                continue

            if raw.startswith("#"):
                anchor = raw[1:]
                if anchor and anchor not in headings_for(DOC_INDEX):
                    errors.append(f"L{i}: broken local anchor '{raw}'")
                continue

            if "#" in raw:
                rel_path, anchor = raw.split("#", 1)
            else:
                rel_path, anchor = raw, ""

            target = (DOC_INDEX.parent / rel_path).resolve()
            if not target.exists():
                errors.append(f"L{i}: missing relative link target '{rel_path}'")
                continue

            if anchor and anchor not in headings_for(target):
                errors.append(
                    f"L{i}: broken anchor '#{anchor}' in '{rel_path}'"
                )

    return errors


def main() -> int:
    """Verify docs exist, contain Markdown, and doc index links are sane."""
    if not DOCS_DIR.exists():
        print("[docs-policy] Missing docs/ directory", file=sys.stderr)
        return 1

    markdown_files = list(DOCS_DIR.rglob("*.md"))
    if not markdown_files:
        print("[docs-policy] No Markdown files found under docs/", file=sys.stderr)
        return 1

    errors = _validate_doc_index()
    if errors:
        print("[docs-policy] FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"[docs-policy] docs/ contains {len(markdown_files)} Markdown file(s); policy satisfied."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
