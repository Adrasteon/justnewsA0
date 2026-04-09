#!/usr/bin/env python3
"""Two-stage retrieval over the local JustNews code index.

Stage A: lexical recall from prebuilt index entries.
Stage B: precision snippets from exact file windows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")
QUOTED_PHRASE_RE = re.compile(r'"([^"]{2,})"')
INDEXABLE_SUFFIXES = {
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
NOISY_QUERY_TOKENS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "over",
    "under",
    "your",
    "about",
    "query",
    "code",
    "file",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query local code index")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--index-dir",
        default=".cache/code_index",
        help="Directory containing index artifacts",
    )
    parser.add_argument("--top-k", type=int, default=12, help="Maximum final matches")
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=5,
        help="Stage-A candidate expansion factor",
    )
    parser.add_argument(
        "--context-lines",
        type=int,
        default=8,
        help="Additional lines around each hit for precision snippets",
    )
    parser.add_argument(
        "--max-snippet-lines",
        type=int,
        default=60,
        help="Maximum snippet length in lines",
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=30,
        help="Mark index stale if manifest is older than this age",
    )
    parser.add_argument(
        "--auto-refresh",
        dest="auto_refresh",
        action="store_true",
        default=True,
        help="Automatically refresh index when stale or missing",
    )
    parser.add_argument(
        "--no-auto-refresh",
        dest="auto_refresh",
        action="store_false",
        help="Disable automatic index refresh",
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
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--chars-per-token",
        type=float,
        default=4.0,
        help="Estimator ratio used for token estimates (chars/token)",
    )
    parser.add_argument(
        "--tokenizer-model",
        default="copilot_chat_selected",
        help=(
            "Tokenizer model name. Use 'copilot_chat_selected' to resolve from "
            "Copilot chat model environment variables."
        ),
    )
    parser.add_argument(
        "--tokenizer-fallback-encoding",
        default="o200k_base",
        help="tiktoken encoding to use when model-specific encoding is unavailable",
    )
    return parser.parse_args()


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _normalize_query_tokens(query: str) -> list[str]:
    raw = _tokenize(query)
    cleaned = [token for token in raw if token not in NOISY_QUERY_TOKENS]
    return cleaned or raw


def _extract_phrases(query: str) -> list[str]:
    phrases = [match.strip().lower() for match in QUOTED_PHRASE_RE.findall(query) if match.strip()]
    return phrases


def _path_tokens(path: str) -> set[str]:
    pieces = re.split(r"[^A-Za-z0-9_]+", path.lower())
    return {token for token in pieces if len(token) >= 2}


def _idf_lookup(entries: list[dict[str, Any]]) -> dict[str, float]:
    doc_count = max(len(entries), 1)
    df: Counter[str] = Counter()
    for entry in entries:
        token_set = set(entry.get("token_set") or [])
        for token in token_set:
            df[token] += 1

    idf: dict[str, float] = {}
    for token, count in df.items():
        idf[token] = math.log((doc_count + 1.0) / (count + 1.0)) + 1.0
    return idf


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
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


def _run_index_build(root: Path, index_dir: Path) -> None:
    cmd = [
        "python3",
        "scripts/indexing/build_code_index.py",
        "--root",
        str(root),
        "--index-dir",
        str(index_dir),
    ]
    subprocess.run(cmd, cwd=root, check=True)


def _append_telemetry(root: Path, telemetry_path: str, event: dict[str, Any]) -> None:
    target = (root / telemetry_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    event_payload = dict(event)
    event_payload["ts_epoch"] = time.time()
    event_payload["ts_iso"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, ensure_ascii=True))
        handle.write("\n")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_stale(manifest_path: Path, max_age_minutes: int) -> bool:
    if not manifest_path.exists():
        return True
    try:
        age_sec = time.time() - manifest_path.stat().st_mtime
    except Exception:
        return True
    return age_sec > max(max_age_minutes, 1) * 60


def _extract_path_from_porcelain(line: str) -> str:
    if not line:
        return ""
    # Format examples:
    # " M path/to/file.py"
    # "R  old/path.py -> new/path.py"
    payload = line[3:].strip() if len(line) >= 4 else line.strip()
    if " -> " in payload:
        payload = payload.split(" -> ", 1)[1].strip()
    return payload


def _sha1_file(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except Exception:
        return None
    digest = hashlib.sha1()
    digest.update(data)
    return digest.hexdigest()


def _has_indexable_git_changes(root: Path, manifest_files: dict[str, Any]) -> bool:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return False

    for line in result.stdout.splitlines():
        status = line[:2] if len(line) >= 2 else ""
        rel = _extract_path_from_porcelain(line)
        if not rel:
            continue
        if rel.startswith(".cache/code_index/"):
            continue
        suffix = Path(rel).suffix.lower()
        if suffix not in INDEXABLE_SUFFIXES:
            continue

        current_path = root / rel
        if not current_path.exists():
            return True

        current_sha1 = _sha1_file(current_path)
        if current_sha1 is None:
            return True

        manifest_entry = manifest_files.get(rel)
        # Untracked files only require refresh when not yet indexed or changed.
        if status == "??":
            if not isinstance(manifest_entry, dict):
                return True
            if str(manifest_entry.get("sha1") or "") != current_sha1:
                return True
            continue

        if not isinstance(manifest_entry, dict):
            return True
        if str(manifest_entry.get("sha1") or "") != current_sha1:
            return True
    return False


def _ensure_index_ready(
    root: Path,
    index_dir: Path,
    auto_refresh: bool,
    max_age_minutes: int,
) -> dict[str, Any]:
    manifest_path = index_dir / "manifest.json"
    entries_path = index_dir / "entries.jsonl"
    manifest = _load_manifest(manifest_path)
    raw_manifest_files = manifest.get("files")
    manifest_files: dict[str, Any] = raw_manifest_files if isinstance(raw_manifest_files, dict) else {}
    stale = _manifest_stale(manifest_path, max_age_minutes=max_age_minutes)
    changed = _has_indexable_git_changes(root, manifest_files=manifest_files)

    needs_build = (not manifest_path.exists()) or (not entries_path.exists()) or stale or changed
    reasons: list[str] = []
    if not manifest_path.exists() or not entries_path.exists():
        reasons.append("missing_index")
    if stale:
        reasons.append("stale_index")
    if changed:
        reasons.append("workspace_changes")

    if not needs_build:
        return {
            "needs_build": False,
            "did_build": False,
            "reasons": [],
        }

    if not auto_refresh:
        reason_text = ", ".join(reasons) or "unknown_reason"
        raise SystemExit(f"Index refresh required ({reason_text}). Re-run with --auto-refresh or run build_code_index.py")

    _run_index_build(root, index_dir)
    return {
        "needs_build": True,
        "did_build": True,
        "reasons": reasons,
    }


def _weighted_overlap_score(
    query_tokens: set[str],
    entry_tokens: set[str],
    idf_lookup: dict[str, float],
) -> float:
    if not query_tokens or not entry_tokens:
        return 0.0
    overlap = query_tokens.intersection(entry_tokens)
    if not overlap:
        return 0.0

    inter_w = sum(idf_lookup.get(token, 1.0) for token in overlap)
    total_q_w = sum(idf_lookup.get(token, 1.0) for token in query_tokens)
    if total_q_w <= 0:
        return 0.0
    return inter_w / total_q_w


def _substring_bonus(query: str, search_text: str) -> float:
    q = query.strip().lower()
    if not q:
        return 0.0
    text = search_text.lower()
    if q in text:
        return min(0.22, 0.02 * max(len(q.split()), 1))
    return 0.0


def _phrase_bonus(phrases: list[str], search_text: str, path_text: str) -> float:
    if not phrases:
        return 0.0
    total = 0.0
    lowered_text = search_text.lower()
    lowered_path = path_text.lower()
    for phrase in phrases:
        if phrase in lowered_path:
            total += 0.22
        elif phrase in lowered_text:
            total += 0.12
    return min(total, 0.5)


def _path_bonus(query_tokens: set[str], path: str) -> float:
    if not query_tokens:
        return 0.0
    path_tok = _path_tokens(path)
    if not path_tok:
        return 0.0

    overlap = query_tokens.intersection(path_tok)
    if not overlap:
        return 0.0
    overlap_count = len(overlap)
    coverage = overlap_count / max(len(query_tokens), 1)
    base = 0.12 if overlap_count >= 2 else 0.06
    return min(0.55, base + 0.45 * coverage)


def _symbol_bonus(query_tokens: set[str], symbol_name: str) -> float:
    if not query_tokens or not symbol_name:
        return 0.0
    sym = symbol_name.lower()
    symbol_tokens = set(_tokenize(sym))

    overlap = query_tokens.intersection(symbol_tokens)
    exact = 1.0 if sym in query_tokens else 0.0
    prefix = 1.0 if any(sym.startswith(token) or token.startswith(sym) for token in query_tokens) else 0.0
    coverage = len(overlap) / max(len(query_tokens), 1)
    return min(0.42, 0.22 * coverage + 0.12 * exact + 0.08 * prefix)


def _rarity_bonus(query_tokens: set[str], entry_tokens: set[str], idf_lookup: dict[str, float]) -> float:
    overlap = query_tokens.intersection(entry_tokens)
    if not overlap:
        return 0.0
    values = [idf_lookup.get(token, 1.0) for token in overlap]
    if not values:
        return 0.0
    return min(0.18, 0.03 * max(values))


def _entry_score(
    query: str,
    query_tokens: set[str],
    query_phrases: list[str],
    idf_lookup: dict[str, float],
    entry: dict[str, Any],
) -> float:
    entry_tokens = set(entry.get("token_set") or [])
    if not query_tokens:
        return 0.0
    overlap_count = len(query_tokens.intersection(entry_tokens))
    if overlap_count == 0:
        return 0.0

    path_text = str(entry.get("path") or "")
    search_text = str(entry.get("search_text") or "")
    symbol_name = str(entry.get("symbol_name") or "")

    lexical = _weighted_overlap_score(query_tokens, entry_tokens, idf_lookup=idf_lookup)
    query_substring_bonus = _substring_bonus(query, search_text)
    phrase_bonus = _phrase_bonus(query_phrases, search_text=search_text, path_text=path_text)
    by_path_bonus = _path_bonus(query_tokens, path=path_text)
    by_symbol_bonus = _symbol_bonus(query_tokens, symbol_name=symbol_name)
    discriminative_bonus = _rarity_bonus(query_tokens, entry_tokens, idf_lookup=idf_lookup)

    has_strong_anchor = by_path_bonus >= 0.12 or by_symbol_bonus >= 0.15 or phrase_bonus > 0

    # Prefer entries that cover multiple query tokens when query is specific.
    min_overlap = 1 if len(query_tokens) <= 2 else 2
    overlap_gate = 0.75 if overlap_count < min_overlap else 1.0

    # Hard filter generic matches for longer queries unless anchored by path/symbol/phrase.
    if len(query_tokens) >= 3 and overlap_count < 2 and not has_strong_anchor:
        return 0.0

    type_boost = 1.0
    if entry.get("entry_type") == "symbol":
        type_boost = 1.12

    score = (
        lexical
        + query_substring_bonus
        + phrase_bonus
        + by_path_bonus
        + by_symbol_bonus
        + discriminative_bonus
    ) * type_boost * overlap_gate
    return score


def _extract_snippet(
    file_path: Path,
    start_line: int,
    end_line: int,
    context_lines: int,
    max_snippet_lines: int,
) -> tuple[int, int, str]:
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = file_path.read_text(encoding="latin-1")

    lines = text.splitlines()
    if not lines:
        return (1, 1, "")

    start = max(1, start_line - context_lines)
    end = min(len(lines), end_line + context_lines)

    if end - start + 1 > max_snippet_lines:
        end = min(len(lines), start + max_snippet_lines - 1)

    snippet = "\n".join(lines[start - 1 : end]).strip()
    return (start, end, snippet)


def _stage_a_rank(
    query: str,
    entries: list[dict[str, Any]],
    top_n: int,
) -> list[dict[str, Any]]:
    query_tokens = set(_normalize_query_tokens(query))
    query_phrases = _extract_phrases(query)
    idf_lookup = _idf_lookup(entries)

    scored: list[dict[str, Any]] = []
    for entry in entries:
        score = _entry_score(
            query,
            query_tokens,
            query_phrases,
            idf_lookup,
            entry,
        )
        if score <= 0:
            continue
        ranked = dict(entry)
        ranked["score"] = round(float(score), 6)
        scored.append(ranked)

    scored.sort(
        key=lambda item: (
            float(item.get("score", 0.0)),
            str(item.get("entry_type", "")) == "symbol",
            len(item.get("search_text") or ""),
        ),
        reverse=True,
    )

    # Light diversity cap to avoid a single file crowding out recall.
    per_path_cap = 3
    path_counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    for item in scored:
        rel_path = str(item.get("path") or "")
        if not rel_path:
            continue
        seen = path_counts.get(rel_path, 0)
        if seen >= per_path_cap:
            continue
        path_counts[rel_path] = seen + 1
        selected.append(item)
        if len(selected) >= top_n:
            break
    return selected


def _stage_b_refine(
    root: Path,
    candidates: list[dict[str, Any]],
    top_k: int,
    context_lines: int,
    max_snippet_lines: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_windows: set[tuple[str, int, int]] = set()

    for entry in candidates:
        rel_path = str(entry.get("path") or "").strip()
        if not rel_path:
            continue
        start_line = int(entry.get("start_line") or 1)
        end_line = int(entry.get("end_line") or start_line)

        file_path = root / rel_path
        if not file_path.exists() or not file_path.is_file():
            continue

        snippet_start, snippet_end, snippet = _extract_snippet(
            file_path,
            start_line,
            end_line,
            context_lines=context_lines,
            max_snippet_lines=max_snippet_lines,
        )
        window_key = (rel_path, snippet_start, snippet_end)
        if window_key in seen_windows:
            continue
        seen_windows.add(window_key)

        results.append(
            {
                "path": rel_path,
                "entry_type": entry.get("entry_type"),
                "symbol_type": entry.get("symbol_type"),
                "symbol_name": entry.get("symbol_name"),
                "score": float(entry.get("score", 0.0)),
                "start_line": int(entry.get("start_line") or 1),
                "end_line": int(entry.get("end_line") or 1),
                "snippet_start": snippet_start,
                "snippet_end": snippet_end,
                "snippet": snippet,
            }
        )
        if len(results) >= top_k:
            break

    return results


def _format_pretty(query: str, results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append(f"Query: {query}")
    lines.append(f"Results: {len(results)}")
    lines.append("")

    for idx, result in enumerate(results, start=1):
        path = result["path"]
        snippet_start = int(result["snippet_start"])
        snippet_end = int(result["snippet_end"])
        score = float(result["score"])
        entry_type = str(result.get("entry_type") or "chunk")
        symbol_name = str(result.get("symbol_name") or "")

        header = f"[{idx}] {path}:{snippet_start}-{snippet_end}  score={score:.4f}  type={entry_type}"
        if symbol_name:
            header += f"  symbol={symbol_name}"
        lines.append(header)
        lines.append("-" * min(len(header), 120))
        snippet = str(result.get("snippet") or "")
        lines.append(snippet)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _estimate_tokens_from_chars(char_count: int, chars_per_token: float) -> int:
    safe_chars = max(int(char_count), 0)
    ratio = chars_per_token if chars_per_token > 0 else 4.0
    return int(math.ceil(safe_chars / ratio)) if safe_chars > 0 else 0


def _load_persisted_chat_model(root: Path) -> tuple[str, str]:
    binding_path = (root / "run" / "copilot_chat_model.env").resolve()
    if not binding_path.exists():
        return "", ""

    try:
        text = binding_path.read_text(encoding="utf-8")
    except Exception:
        return "", ""

    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"").strip("'")

    model = str(values.get("COPILOT_CHAT_MODEL") or "").strip()
    source = str(values.get("COPILOT_CHAT_MODEL_SOURCE") or "persisted").strip()
    return model, source


def _resolve_tokenizer_model(tokenizer_model_arg: str, root: Path) -> tuple[str, str]:
    requested = str(tokenizer_model_arg or "").strip()
    if requested and requested.lower() != "copilot_chat_selected":
        return requested, "cli"

    candidates = [
        "COPILOT_CHAT_MODEL",
        "GITHUB_COPILOT_CHAT_MODEL",
        "VSCODE_COPILOT_CHAT_MODEL",
        "CHAT_MODEL",
        "GITHUB_COPILOT_MODEL",
    ]
    for key in candidates:
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value, f"env:{key}"

    persisted_model, persisted_source = _load_persisted_chat_model(root)
    if persisted_model:
        return persisted_model, f"file:{persisted_source}"

    # Default to the active assistant model family if no explicit session value is exposed.
    return "gpt-5.4", "default"


def _encoding_hint_for_model(model_name: str, fallback_encoding: str) -> str:
    lowered = str(model_name or "").strip().lower()
    if not lowered:
        return fallback_encoding

    if any(token in lowered for token in ("gpt-5", "gpt-4.1", "gpt-4o", "o3", "o4")):
        return "o200k_base"
    if any(token in lowered for token in ("gpt-4", "gpt-3.5", "cl100k")):
        return "cl100k_base"
    return fallback_encoding


def _count_tokens_model_aware(
    text: str,
    *,
    tokenizer_model: str,
    fallback_encoding: str,
    chars_per_token: float,
) -> dict[str, Any]:
    body = str(text or "")
    if not body:
        return {
            "tokens": 0,
            "backend": "none",
            "encoding": "",
            "exact": True,
        }

    try:
        import tiktoken  # type: ignore

        try:
            encoding = tiktoken.encoding_for_model(tokenizer_model)
            encoding_name = str(getattr(encoding, "name", "")) or _encoding_hint_for_model(
                tokenizer_model,
                fallback_encoding,
            )
            tokens = len(encoding.encode(body))
            return {
                "tokens": int(tokens),
                "backend": "tiktoken:model",
                "encoding": encoding_name,
                "exact": True,
            }
        except Exception:
            encoding_name = _encoding_hint_for_model(tokenizer_model, fallback_encoding)
            encoding = tiktoken.get_encoding(encoding_name)
            tokens = len(encoding.encode(body))
            return {
                "tokens": int(tokens),
                "backend": "tiktoken:encoding",
                "encoding": encoding_name,
                "exact": True,
            }
    except Exception:
        fallback_tokens = _estimate_tokens_from_chars(len(body), chars_per_token)
        return {
            "tokens": int(fallback_tokens),
            "backend": "chars_per_token",
            "encoding": "",
            "exact": False,
        }


def main() -> int:
    started = time.perf_counter()
    args = parse_args()
    root = Path(args.root).resolve()
    index_dir = (root / args.index_dir).resolve()
    entries_path = index_dir / "entries.jsonl"
    refresh_state = _ensure_index_ready(
        root,
        index_dir,
        auto_refresh=bool(args.auto_refresh),
        max_age_minutes=max(int(args.max_age_minutes), 1),
    )

    entries = _load_jsonl(entries_path)
    if not entries:
        raise SystemExit(
            "No index entries found. Run scripts/indexing/build_code_index.py first."
        )

    candidate_count = max(int(args.top_k) * max(int(args.candidate_multiplier), 1), int(args.top_k))
    stage_a = _stage_a_rank(args.query, entries, top_n=candidate_count)
    stage_b = _stage_b_refine(
        root,
        stage_a,
        top_k=max(int(args.top_k), 1),
        context_lines=max(int(args.context_lines), 0),
        max_snippet_lines=max(int(args.max_snippet_lines), 10),
    )

    # Baseline approximation for "no-index narrowing": include all Stage-A
    # candidates, then compare against final Stage-B top-k payload size.
    baseline_results = _stage_b_refine(
        root,
        stage_a,
        top_k=max(len(stage_a), 1),
        context_lines=max(int(args.context_lines), 0),
        max_snippet_lines=max(int(args.max_snippet_lines), 10),
    )

    output = {
        "query": args.query,
        "index_dir": index_dir.as_posix(),
        "candidates_considered": len(stage_a),
        "results": stage_b,
    }

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=True))
    else:
        print(_format_pretty(args.query, stage_b), end="")

    if not args.no_telemetry:
        try:
            top_result = stage_b[0] if stage_b else {}
            snippet_chars = sum(len(str(item.get("snippet") or "")) for item in stage_b)
            baseline_snippet_chars = sum(
                len(str(item.get("snippet") or "")) for item in baseline_results
            )

            tokenizer_model, tokenizer_model_source = _resolve_tokenizer_model(
                args.tokenizer_model,
                root,
            )
            indexed_text = "\n\n".join(str(item.get("snippet") or "") for item in stage_b)
            baseline_text = "\n\n".join(
                str(item.get("snippet") or "") for item in baseline_results
            )

            indexed_token_metrics = _count_tokens_model_aware(
                indexed_text,
                tokenizer_model=tokenizer_model,
                fallback_encoding=str(args.tokenizer_fallback_encoding),
                chars_per_token=float(args.chars_per_token),
            )
            baseline_token_metrics = _count_tokens_model_aware(
                baseline_text,
                tokenizer_model=tokenizer_model,
                fallback_encoding=str(args.tokenizer_fallback_encoding),
                chars_per_token=float(args.chars_per_token),
            )

            chars_per_token = float(args.chars_per_token)
            indexed_tokens = int(indexed_token_metrics.get("tokens") or 0)
            baseline_tokens = int(baseline_token_metrics.get("tokens") or 0)
            savings_tokens = max(baseline_tokens - indexed_tokens, 0)
            savings_pct = (
                (savings_tokens / baseline_tokens) * 100.0
                if baseline_tokens > 0
                else 0.0
            )
            _append_telemetry(
                root,
                args.telemetry_path,
                {
                    "event_type": "index_query",
                    "query": args.query,
                    "query_token_count": len(_normalize_query_tokens(args.query)),
                    "auto_refresh_enabled": bool(args.auto_refresh),
                    "refresh_needed": bool(refresh_state.get("needs_build", False)),
                    "refresh_performed": bool(refresh_state.get("did_build", False)),
                    "refresh_reasons": list(refresh_state.get("reasons") or []),
                    "candidates_considered": len(stage_a),
                    "results_count": len(stage_b),
                    "top_path": str(top_result.get("path") or ""),
                    "top_score": float(top_result.get("score", 0.0) or 0.0),
                    "snippet_chars_total": int(snippet_chars),
                    "baseline_snippet_chars_total": int(baseline_snippet_chars),
                    "tokenizer_model": tokenizer_model,
                    "tokenizer_model_source": tokenizer_model_source,
                    "tokenizer_backend": str(indexed_token_metrics.get("backend") or ""),
                    "tokenizer_encoding": str(indexed_token_metrics.get("encoding") or ""),
                    "exact_token_counting": bool(indexed_token_metrics.get("exact", False)),
                    "indexed_snippet_tokens": int(indexed_tokens),
                    "baseline_snippet_tokens": int(baseline_tokens),
                    "token_savings": int(savings_tokens),
                    "token_savings_pct": round(float(savings_pct), 3),
                    "token_estimator": "chars_per_token",
                    "chars_per_token": float(chars_per_token),
                    # Backward compatibility fields retained for existing dashboards.
                    "indexed_snippet_tokens_estimate": int(indexed_tokens),
                    "baseline_snippet_tokens_estimate": int(baseline_tokens),
                    "estimated_token_savings": int(savings_tokens),
                    "estimated_token_savings_pct": round(float(savings_pct), 3),
                    "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
                },
            )
        except Exception:
            # Telemetry must never fail query results.
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
