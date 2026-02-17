#!/usr/bin/env python3
"""
deprecate_dialogpt.py

Finds occurrences of DialoGPT (deprecated) in the repository and offers safe replacements.

Behavior:
- Dry-run by default: lists files and proposed edits.
- Use --apply to write changes (backups created with .bak extension).
- For Python files: replaces literal model ids like os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2") and
  os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2") with an environment-driven expression:
    os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2")
  and ensures `import os` exists.
- In comments/docstrings and non-Python text files: annotates occurrences of "DialoGPT (deprecated)"
  with "DialoGPT (deprecated) (deprecated)" or replaces model ids with "distilgpt2 (deprecated)".

Run: python scripts/deprecate_dialogpt.py --help
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PY_PATTERN = re.compile(r"\.py$", re.IGNORECASE)
TEXT_EXTS = {".md", ".rst", ".txt", ".yaml", ".yml", ".json", ".ini", ".cfg"}

# directories to exclude from scanning (model caches, large artifacts)
EXCLUDE_DIRS = {".git", ".cache", "model_cache", "models", "archive_obsolete_files"}

# patterns to replace: tuple(pattern, replacement_fn, description)
MODEL_LITERALS = [
    os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2"),
    os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2"),
    os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2"),
]


def find_files(root: Path) -> list[Path]:
    files = []
    for p in root.rglob("*"):
        if p.is_file():
            # skip excluded directories anywhere in the path
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            files.append(p)
    return files


def make_backup(path: Path):
    bak = path.with_suffix(path.suffix + ".bak")
    if not bak.exists():
        path.rename(bak)
        return bak
    else:
        # if backup exists, don't overwrite
        return None


def ensure_import_os(lines: list[str]) -> list[str]:
    joined = "\n".join(lines[:50])  # search top of file
    if re.search(r"(^|\n)\s*import\s+os(\s|$)", joined):
        return lines
    # Find insertion point after shebang and existing imports
    insert_at = 0
    for i, ln in enumerate(lines[:60]):
        if ln.startswith("#!"):
            insert_at = i + 1
        elif ln.strip().startswith("import") or ln.strip().startswith("from"):
            insert_at = i + 1
    lines.insert(insert_at, "import os")
    return lines


def process_python_file(path: Path, apply: bool) -> tuple[bool, list[str]]:
    text = path.read_text(encoding="utf-8")
    changed = False
    notes = []
    # Replace literal model ids inside quotes
    for lit in MODEL_LITERALS:
        # replace quoted occurrences
        pattern = re.compile(rf"([\'\"]){re.escape(lit)}([\'\"])")
        if pattern.search(text):
            repl = 'os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2")'
            text = pattern.sub(repl, text)
            changed = True
            notes.append(f"Replaced literal {lit} with env-driven fallback")

    # Replace bare word "DialoGPT (deprecated)" in comments and docstrings: annotate as deprecated
    if "DialoGPT (deprecated)" in text:
        # Only change occurrences outside code strings? Simpler: annotate common comment patterns
        text = re.sub(r"(\bDialoGPT\b)", r"DialoGPT (deprecated) (deprecated)", text)
        changed = True
        notes.append("Annotated DialoGPT (deprecated) mentions as deprecated")

    if changed:
        # ensure import os exists
        lines = text.splitlines()
        lines = ensure_import_os(lines)
        newtext = "\n".join(lines)
        if apply:
            # backup file
            bak_path = path.with_suffix(path.suffix + ".bak")
            if not bak_path.exists():
                path.rename(bak_path)
                path.write_text(newtext, encoding="utf-8")
            else:
                # write new file directly, but first create .bak.timestamp
                ts_bak = path.with_suffix(path.suffix + ".bak2")
                path.rename(ts_bak)
                path.write_text(newtext, encoding="utf-8")
        return True, notes
    return False, notes


def process_text_file(path: Path, apply: bool) -> tuple[bool, list[str]]:
    text = path.read_text(encoding="utf-8")
    changed = False
    notes = []
    if "DialoGPT (deprecated)" in text:
        text2 = text.replace(
            os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2"),
            "distilgpt2 (deprecated)",
        )
        text2 = text2.replace(
            os.environ.get("DIALOGPT_REPLACEMENT_MODEL", "distilgpt2"),
            "distilgpt2 (deprecated)",
        )
        text2 = text2.replace(
            "DialoGPT (deprecated)", "DialoGPT (deprecated) (deprecated)"
        )
        if text2 != text:
            changed = True
            notes.append("Annotated DialoGPT (deprecated) mention(s) in text file")
            if apply:
                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():
                    path.rename(bak)
                    path.write_text(text2, encoding="utf-8")
                else:
                    ts_bak = path.with_suffix(path.suffix + ".bak2")
                    path.rename(ts_bak)
                    path.write_text(text2, encoding="utf-8")
    return changed, notes


def run(dry_run: bool = True) -> int:
    files = find_files(REPO_ROOT)
    total = 0
    changed_files = []
    for f in files:
        if f.match("**/*.py"):
            if "site-packages" in str(f):
                continue
            with f.open("r", encoding="utf-8", errors="ignore") as fh:
                data = fh.read()
            if "DialoGPT (deprecated)" in data or any(
                lit in data for lit in MODEL_LITERALS
            ):
                total += 1
                ok, notes = process_python_file(f, apply=not dry_run)
                if ok:
                    changed_files.append((f, notes))
        else:
            if f.suffix.lower() in TEXT_EXTS:
                data = f.read_text(encoding="utf-8", errors="ignore")
                if "DialoGPT (deprecated)" in data:
                    total += 1
                    ok, notes = process_text_file(f, apply=not dry_run)
                    if ok:
                        changed_files.append((f, notes))

    # report
    if dry_run:
        print(
            f"Dry-run: found {total} files with DialoGPT (deprecated) references. No files modified."
        )
    else:
        print(
            f"Applied changes to {len(changed_files)} files. Backups saved with .bak suffix where applicable."
        )

    for p, notes in changed_files:
        print(f"- {p}:")
        for n in notes:
            print(f"    * {n}")

    return 0


def main():
    p = argparse.ArgumentParser(
        description="Deprecate DialoGPT (deprecated) occurrences across workspace"
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (writes files). Default: dry-run",
    )
    args = p.parse_args()
    rc = run(dry_run=not args.apply)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
