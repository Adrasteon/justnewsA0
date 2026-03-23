#!/usr/bin/env python3
"""Incremental local code index builder for JustNews.

The index is intentionally lightweight and dependency-free so it can run in
CI/dev-container environments without extra packages.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INDEX_VERSION = 1
DEFAULT_INCLUDE_SUFFIXES = {
    ".py",
    ".md",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".sh",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")


@dataclass
class FileMeta:
    sha1: str
    size: int
    mtime: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build incremental local code index")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--index-dir",
        default=".cache/code_index",
        help="Directory for index artifacts",
    )
    parser.add_argument(
        "--chunk-lines",
        type=int,
        default=80,
        help="Max lines per text chunk",
    )
    parser.add_argument(
        "--chunk-overlap-lines",
        type=int,
        default=15,
        help="Overlapping lines between chunks",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full rebuild (ignore previous manifest)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress details",
    )
    parser.add_argument(
        "--telemetry-path",
        default="run/indexing_telemetry.jsonl",
        help="Path for telemetry JSONL events",
    )
    parser.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Disable telemetry logging",
    )
    return parser.parse_args()


def _append_telemetry(root: Path, telemetry_path: str, event: dict[str, Any]) -> None:
    target = (root / telemetry_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    event_payload = dict(event)
    event_payload["ts_epoch"] = time.time()
    event_payload["ts_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, ensure_ascii=True))
        handle.write("\n")


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _sha1_bytes(data: bytes) -> str:
    digest = hashlib.sha1()
    digest.update(data)
    return digest.hexdigest()


def _run_git_ls_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return []

    files: list[Path] = []
    for line in result.stdout.splitlines():
        rel = line.strip()
        if not rel:
            continue
        files.append(root / rel)
    return files


def _run_git_status_untracked(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return []

    files: list[Path] = []
    for line in result.stdout.splitlines():
        line = line.rstrip()
        if not line.startswith("?? "):
            continue
        rel = line[3:].strip()
        if not rel:
            continue
        candidate = root / rel
        if candidate.is_dir():
            for current_root, _dirs, child_files in os.walk(candidate):
                for child in child_files:
                    files.append(Path(current_root) / child)
            continue
        files.append(candidate)
    return files


def _iter_candidate_files(root: Path) -> list[Path]:
    tracked = _run_git_ls_files(root)
    if tracked:
        # Include untracked files so new local scripts/docs are retrievable
        # before they are committed.
        untracked = _run_git_status_untracked(root)
        seen: set[Path] = set()
        merged: list[Path] = []
        for item in tracked + untracked:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
        return merged

    candidates: list[Path] = []
    for current_root, dirs, files in os.walk(root):
        if ".git" in dirs:
            dirs.remove(".git")
        if ".venv" in dirs:
            dirs.remove(".venv")
        for file_name in files:
            candidates.append(Path(current_root) / file_name)
    return candidates


def _is_indexable(path: Path, root: Path) -> bool:
    if not path.is_file():
        return False
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False

    rel_str = rel.as_posix()
    if rel_str.startswith(".git/") or rel_str.startswith(".venv/"):
        return False
    if "/.git/" in rel_str or "/.venv/" in rel_str:
        return False
    if rel_str.startswith(".cache/code_index/"):
        return False
    return path.suffix.lower() in DEFAULT_INCLUDE_SUFFIXES


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None
    except Exception:
        return None


def _file_meta(path: Path) -> FileMeta | None:
    try:
        data = path.read_bytes()
        stat = path.stat()
    except Exception:
        return None
    return FileMeta(sha1=_sha1_bytes(data), size=stat.st_size, mtime=stat.st_mtime)


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    running = 0
    for line in text.splitlines(keepends=True):
        running += len(line)
        offsets.append(running)
    return offsets


def _extract_window_text(text: str, start_line: int, end_line: int) -> str:
    lines = text.splitlines()
    start_idx = max(start_line - 1, 0)
    end_idx = min(end_line, len(lines))
    return "\n".join(lines[start_idx:end_idx]).strip()


def _python_symbol_entries(rel_path: str, text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        module = ast.parse(text)
    except SyntaxError:
        return entries

    for node in ast.walk(module):
        symbol_kind: str | None = None
        symbol_name: str | None = None
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.ClassDef):
            symbol_kind = "class"
            symbol_name = node.name
        elif isinstance(node, ast.FunctionDef):
            symbol_kind = "function"
            symbol_name = node.name
        elif isinstance(node, ast.AsyncFunctionDef):
            symbol_kind = "async_function"
            symbol_name = node.name

        if not symbol_kind or not symbol_name:
            continue

        start = int(getattr(node, "lineno", 1))
        end = int(getattr(node, "end_lineno", start))
        block_text = _extract_window_text(text, start, min(end, start + 60))
        doc = ast.get_docstring(node)
        searchable = "\n".join(
            chunk for chunk in [symbol_name, doc or "", block_text] if chunk
        )
        tokens = _tokenize(searchable)
        entries.append(
            {
                "entry_type": "symbol",
                "symbol_type": symbol_kind,
                "symbol_name": symbol_name,
                "path": rel_path,
                "start_line": start,
                "end_line": end,
                "search_text": searchable,
                "tokens": tokens,
            }
        )
    return entries


def _chunk_entries(
    rel_path: str,
    text: str,
    chunk_lines: int,
    overlap_lines: int,
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    if not lines:
        return []

    entries: list[dict[str, Any]] = []
    step = max(chunk_lines - overlap_lines, 1)
    start_idx = 0
    chunk_id = 0
    while start_idx < len(lines):
        end_idx = min(start_idx + chunk_lines, len(lines))
        snippet = "\n".join(lines[start_idx:end_idx]).strip()
        if snippet:
            start_line = start_idx + 1
            end_line = end_idx
            tokens = _tokenize(snippet)
            entries.append(
                {
                    "entry_type": "chunk",
                    "chunk_id": chunk_id,
                    "path": rel_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "search_text": snippet,
                    "tokens": tokens,
                }
            )
            chunk_id += 1
        if end_idx >= len(lines):
            break
        start_idx += step
    return entries


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _load_existing_entries(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
    return entries


def _entries_by_path(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        grouped.setdefault(path, []).append(entry)
    return grouped


def _index_file(
    root: Path,
    file_path: Path,
    chunk_lines: int,
    overlap_lines: int,
) -> tuple[FileMeta | None, list[dict[str, Any]]]:
    rel = file_path.relative_to(root).as_posix()
    meta = _file_meta(file_path)
    if meta is None:
        return None, []

    text = _read_text(file_path)
    if text is None:
        return None, []

    entries = _chunk_entries(rel, text, chunk_lines=chunk_lines, overlap_lines=overlap_lines)
    if file_path.suffix.lower() == ".py":
        entries.extend(_python_symbol_entries(rel, text))

    # Keep token payload compact for storage.
    for entry in entries:
        entry["token_set"] = sorted(set(entry.pop("tokens", [])))

    return meta, entries


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=True))
            handle.write("\n")


def main() -> int:
    started = time.perf_counter()
    args = parse_args()
    root = Path(args.root).resolve()
    index_dir = (root / args.index_dir).resolve()
    index_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = index_dir / "manifest.json"
    entries_path = index_dir / "entries.jsonl"

    previous_manifest = {} if args.full else _load_manifest(manifest_path)
    previous_files = previous_manifest.get("files") if isinstance(previous_manifest.get("files"), dict) else {}

    existing_entries = [] if args.full else _load_existing_entries(entries_path)
    existing_by_path = _entries_by_path(existing_entries)

    candidates = [path for path in _iter_candidate_files(root) if _is_indexable(path, root)]

    next_files: dict[str, Any] = {}
    next_entries_by_path: dict[str, list[dict[str, Any]]] = {}

    reused_count = 0
    reindexed_count = 0

    for file_path in sorted(candidates):
        rel = file_path.relative_to(root).as_posix()
        current_meta = _file_meta(file_path)
        if current_meta is None:
            continue

        previous_meta = previous_files.get(rel) if isinstance(previous_files, dict) else None
        unchanged = bool(
            previous_meta
            and isinstance(previous_meta, dict)
            and previous_meta.get("sha1") == current_meta.sha1
            and rel in existing_by_path
        )

        if unchanged:
            next_entries_by_path[rel] = existing_by_path.get(rel, [])
            reused_count += 1
        else:
            meta, new_entries = _index_file(
                root,
                file_path,
                chunk_lines=max(args.chunk_lines, 10),
                overlap_lines=max(args.chunk_overlap_lines, 0),
            )
            if meta is None:
                continue
            next_entries_by_path[rel] = new_entries
            reindexed_count += 1
            current_meta = meta
            if args.verbose:
                print(f"indexed: {rel} ({len(new_entries)} entries)")

        next_files[rel] = {
            "sha1": current_meta.sha1,
            "size": current_meta.size,
            "mtime": current_meta.mtime,
            "entries": len(next_entries_by_path.get(rel, [])),
        }

    # Flatten entries preserving path + line ordering for deterministic output.
    all_entries: list[dict[str, Any]] = []
    for rel_path in sorted(next_entries_by_path.keys()):
        path_entries = sorted(
            next_entries_by_path[rel_path],
            key=lambda item: (
                int(item.get("start_line", 1)),
                int(item.get("end_line", 1)),
                str(item.get("entry_type", "")),
                str(item.get("symbol_name", "")),
            ),
        )
        all_entries.extend(path_entries)

    _write_jsonl(entries_path, all_entries)

    manifest = {
        "index_version": INDEX_VERSION,
        "root": root.as_posix(),
        "files_indexed": len(next_files),
        "entries_total": len(all_entries),
        "chunk_lines": int(args.chunk_lines),
        "chunk_overlap_lines": int(args.chunk_overlap_lines),
        "files": next_files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    summary = {
        "files_indexed": len(next_files),
        "entries_total": len(all_entries),
        "reused_files": reused_count,
        "reindexed_files": reindexed_count,
        "index_dir": index_dir.as_posix(),
        "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=True))

    if not args.no_telemetry:
        try:
            _append_telemetry(
                root,
                args.telemetry_path,
                {
                    "event_type": "index_build",
                    "mode": "full" if args.full else "incremental",
                    "files_indexed": int(summary["files_indexed"]),
                    "entries_total": int(summary["entries_total"]),
                    "reused_files": int(summary["reused_files"]),
                    "reindexed_files": int(summary["reindexed_files"]),
                    "duration_ms": float(summary["duration_ms"]),
                },
            )
        except Exception:
            # Telemetry must never fail the primary indexing workflow.
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
