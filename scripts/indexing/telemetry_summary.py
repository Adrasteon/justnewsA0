#!/usr/bin/env python3
"""Summarize lightweight indexing telemetry events."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize indexing telemetry")
    parser.add_argument(
        "--path",
        default="run/indexing_telemetry.jsonl",
        help="Telemetry JSONL file path",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=500,
        help="Only consider the last N events",
    )
    return parser.parse_args()


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except Exception:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    return events


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _read_int_with_fallback(event: dict[str, Any], keys: list[str]) -> int:
    for key in keys:
        if key in event:
            return _safe_int(event.get(key))
    return 0


def _read_float_with_fallback(event: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        if key in event:
            return _safe_float(event.get(key))
    return 0.0


def main() -> int:
    args = parse_args()
    path = Path(args.path).resolve()
    events = _load_events(path)
    if not events:
        print(json.dumps({"path": path.as_posix(), "events": 0}, indent=2, ensure_ascii=True))
        return 0

    selected = events[-max(int(args.last), 1) :]

    build_events = [event for event in selected if event.get("event_type") == "index_build"]
    query_events = [event for event in selected if event.get("event_type") == "index_query"]
    auto_events = [event for event in selected if event.get("event_type") == "index_autoupdate"]
    savings_query_events = [
        event
        for event in query_events
        if any(
            key in event
            for key in (
                "token_savings",
                "estimated_token_savings",
                "baseline_snippet_tokens",
                "baseline_snippet_tokens_estimate",
                "indexed_snippet_tokens",
                "indexed_snippet_tokens_estimate",
            )
        )
    ]
    exact_token_events = [
        event
        for event in savings_query_events
        if bool(event.get("exact_token_counting", False))
    ]

    query_durations = [_safe_float(event.get("duration_ms")) for event in query_events]
    build_durations = [_safe_float(event.get("duration_ms")) for event in build_events]

    refresh_performed = [event for event in query_events if bool(event.get("refresh_performed"))]
    refresh_needed = [event for event in query_events if bool(event.get("refresh_needed"))]

    candidate_counts = [_safe_int(event.get("candidates_considered")) for event in query_events]
    snippet_chars = [_safe_int(event.get("snippet_chars_total")) for event in query_events]
    baseline_snippet_chars = [
        _safe_int(event.get("baseline_snippet_chars_total")) for event in savings_query_events
    ]
    indexed_tokens_est = [
        _read_int_with_fallback(
            event,
            ["indexed_snippet_tokens", "indexed_snippet_tokens_estimate"],
        )
        for event in savings_query_events
    ]
    baseline_tokens_est = [
        _read_int_with_fallback(
            event,
            ["baseline_snippet_tokens", "baseline_snippet_tokens_estimate"],
        )
        for event in savings_query_events
    ]
    token_savings_est = [
        _read_int_with_fallback(event, ["token_savings", "estimated_token_savings"])
        for event in savings_query_events
    ]
    token_savings_pct_est = [
        _read_float_with_fallback(event, ["token_savings_pct", "estimated_token_savings_pct"])
        for event in savings_query_events
    ]

    tokenizer_backends: dict[str, int] = {}
    tokenizer_models: dict[str, int] = {}
    for event in savings_query_events:
        backend = str(event.get("tokenizer_backend") or "").strip()
        if backend:
            tokenizer_backends[backend] = tokenizer_backends.get(backend, 0) + 1
        model = str(event.get("tokenizer_model") or "").strip()
        if model:
            tokenizer_models[model] = tokenizer_models.get(model, 0) + 1

    top_tokenizer_backends = sorted(
        tokenizer_backends.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:10]
    top_tokenizer_models = sorted(
        tokenizer_models.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:10]

    top_paths: dict[str, int] = {}
    for event in query_events:
        path_key = str(event.get("top_path") or "").strip()
        if not path_key:
            continue
        top_paths[path_key] = top_paths.get(path_key, 0) + 1

    top_paths_sorted = sorted(top_paths.items(), key=lambda item: item[1], reverse=True)[:10]

    summary = {
        "path": path.as_posix(),
        "events_considered": len(selected),
        "event_breakdown": {
            "index_build": len(build_events),
            "index_query": len(query_events),
            "index_autoupdate": len(auto_events),
        },
        "query_metrics": {
            "count": len(query_events),
            "avg_duration_ms": round(mean(query_durations), 3) if query_durations else 0.0,
            "avg_candidates_considered": round(mean(candidate_counts), 3) if candidate_counts else 0.0,
            "avg_snippet_chars_total": round(mean(snippet_chars), 3) if snippet_chars else 0.0,
            "token_savings_events_count": len(savings_query_events),
            "exact_token_count_events_count": len(exact_token_events),
            "avg_baseline_snippet_chars_total": round(mean(baseline_snippet_chars), 3)
            if baseline_snippet_chars
            else 0.0,
            "avg_indexed_snippet_tokens_estimate": round(mean(indexed_tokens_est), 3)
            if indexed_tokens_est
            else 0.0,
            "avg_baseline_snippet_tokens_estimate": round(mean(baseline_tokens_est), 3)
            if baseline_tokens_est
            else 0.0,
            "avg_estimated_token_savings": round(mean(token_savings_est), 3)
            if token_savings_est
            else 0.0,
            "avg_estimated_token_savings_pct": round(mean(token_savings_pct_est), 3)
            if token_savings_pct_est
            else 0.0,
            "sum_estimated_token_savings": int(sum(token_savings_est)) if token_savings_est else 0,
            "top_tokenizer_backends": [
                {"backend": name, "count": count} for name, count in top_tokenizer_backends
            ],
            "top_tokenizer_models": [
                {"model": name, "count": count} for name, count in top_tokenizer_models
            ],
            "refresh_needed_rate": round((len(refresh_needed) / len(query_events)) * 100.0, 3)
            if query_events
            else 0.0,
            "refresh_performed_rate": round((len(refresh_performed) / len(query_events)) * 100.0, 3)
            if query_events
            else 0.0,
            "top_paths": [{"path": path_key, "count": count} for path_key, count in top_paths_sorted],
        },
        "build_metrics": {
            "count": len(build_events),
            "avg_duration_ms": round(mean(build_durations), 3) if build_durations else 0.0,
            "avg_reindexed_files": round(
                mean([_safe_int(event.get("reindexed_files")) for event in build_events]),
                3,
            )
            if build_events
            else 0.0,
            "avg_reused_files": round(
                mean([_safe_int(event.get("reused_files")) for event in build_events]),
                3,
            )
            if build_events
            else 0.0,
        },
        "autoupdate_metrics": {
            "count": len(auto_events),
            "nonzero_exit_codes": [
                _safe_int(event.get("exit_code"))
                for event in auto_events
                if _safe_int(event.get("exit_code")) != 0
            ],
        },
    }

    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
