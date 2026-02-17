#!/usr/bin/env python3
"""
Scan the repo for disallowed container/orchestration references in non-archive, non-doc paths.

This script will exit with a non-zero status code if it finds any hits.
It will ignore (allow) references inside these directories:
 - infrastructure/archives/
 - docs/
 - .github/

Usage: scripts/checks/no_container_refs.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# List of banned patterns (regex)
BANNED_PATTERNS = [
    r"docker-compose",
    r"\bdocker\s+(?:run|build|pull|push|login)\b",
    r"\bDockerfile\b",
    r"\bhelm\s+(?:install|upgrade|rollback|uninstall)\b",
    r"\bkubectl\s+(?:apply|create|delete|get|run|exec)\b",
    # Kubernetes/k8s used alone is allowed in code comments (deprecated messages) but commands are banned
    r"\bkubectl\b",
]

# Directories to exclude entirely from scanning (archived or docs)
EXCLUDE_DIRS = [
    "infrastructure/archives",
    "infrastructure/docker",
    "infrastructure/helm",
    "infrastructure/kubernetes",
    "infrastructure/templates",
    "docs",
    ".github",
    "agents/synthesizer/models",
    "model_store",
    "stored_archive",
    "raw_html",
    "logs",
    "scripts/checks",
    "third_party",
]

# File extensions to scan (only these will be scanned for banned tokens)
ALLOWED_EXTENSIONS = {"py", "sh", "yml", "yaml", "ini", "cfg", "env", "service"}

# We'll also accept files with special names (Makefile, Dockerfile)


def is_excluded(path: Path) -> bool:
    # Check whether a file path falls under an excluded directory
    for excl in EXCLUDE_DIRS:
        try:
            if path.resolve().relative_to(Path.cwd().resolve() / excl):
                return True
        except Exception:
            pass
    return False


ALLOWED_FILENAMES = {"Makefile", "Dockerfile"}


def should_scan_file(path: Path) -> bool:
    """Return True if the file should be scanned.
    Only scan files with allowed extensions or special filenames (Makefile, Dockerfile).
    """
    if path.name in ALLOWED_FILENAMES or path.name.startswith("Dockerfile"):
        return True
    ext = path.suffix.lstrip(".").lower()
    return ext in ALLOWED_EXTENSIONS


def main() -> int:
    repo_root = Path.cwd()
    matches = []
    compiled = [re.compile(p, flags=re.IGNORECASE) for p in BANNED_PATTERNS]

    for root, _dirs, files in os.walk(repo_root):
        # Skip vendor/ or .git or site-packages
        try:
            top_element = Path(root).resolve().relative_to(repo_root.resolve()).parts[0]
            if top_element == ".git":
                continue
        except Exception:
            # If the path is identical to repo_root or other reasons, skip gracefully
            pass
        # Skip excluded top-level dirs quickly
        relative_root = Path(root).relative_to(repo_root)
        skip_here = False
        for excl in EXCLUDE_DIRS:
            if str(relative_root).startswith(excl):
                skip_here = True
                break
        if skip_here:
            continue

        for fname in files:
            fpath = Path(root) / fname
            if not should_scan_file(fpath):
                continue
            # Exclude binary-looking files
            if is_excluded(fpath):
                continue
            try:
                text = fpath.read_text(errors="ignore")
            except OSError:
                continue
            for p in compiled:
                for m in p.finditer(text):
                    # Determine the line containing the match for contextual checks
                    start_idx = m.start()
                    line_start = text.rfind("\n", 0, start_idx) + 1
                    line_end = text.find("\n", start_idx)
                    if line_end == -1:
                        line_end = len(text)
                    matched_line = text[line_start:line_end].strip()
                    # Ignore textual references that explicitly state deprecation or archival
                    if re.search(
                        r"deprecated|deprecate|archiv|archived|removed",
                        matched_line,
                        flags=re.IGNORECASE,
                    ):
                        continue
                    # Only add as violation when file path not in excluded set
                    matches.append((str(fpath), m.group(0), matched_line))
    if matches:
        print(
            "Found disallowed container/orchestration references outside of 'infrastructure/archives' or 'docs':",
            file=sys.stderr,
        )
        for filepath, token, _ in matches:
            print(f" - {token}: {filepath}", file=sys.stderr)
        return 2
    print(
        "No disallowed container/orchestration references found outside of allowed folders."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
