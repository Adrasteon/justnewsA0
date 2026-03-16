#!/usr/bin/env python3
"""Run an end-to-end smoke pass for the refactored JustNews workflow.

This script focuses on prototype functionality (code path), not dashboards/docs.
It can inspect queue readiness and optionally execute the orchestrator policy chain.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("JUSTNEWS_DB_EMBEDDING_ENABLED", "0")

from database.utils.migrated_database_utils import create_database_service
from agents.workflow_orchestrator.policies import (
    AnalysisToEmbeddingPolicy,
    AnalysisToFactCheckPolicy,
    ClusterToSynthesisPolicy,
    IncrementalClusteringPolicy,
    IngestionToAnalysisPolicy,
    SynthesisToCritiquePolicy,
    SynthesisToPublishingPolicy,
)


@dataclass
class PolicyResult:
    name: str
    found_items: int
    sampled_items: list[Any]
    executed: bool
    execution_error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run refactor E2E smoke check")
    parser.add_argument(
        "--mcp-bus-url",
        default="http://localhost:8000",
        help="MCP bus base URL used by workflow policies",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of items each policy checks/executes",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute policy actions after queue check (default is check-only)",
    )
    parser.add_argument(
        "--out-dir",
        default="logs/operations/e2e_refactor_smoke",
        help="Directory for JSON/Markdown report output",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.25,
        help="Small delay between policy executions",
    )
    return parser.parse_args()


def _load_recent_state() -> dict[str, Any]:
    db_service = create_database_service()
    db_service.ensure_conn()
    cursor = db_service.mb_conn.cursor()

    snapshot: dict[str, Any] = {}
    try:
        cursor.execute(
            """
            SELECT story_id, is_published, critique_status, updated_at, synth_metadata
            FROM synthesized_articles
            ORDER BY updated_at DESC
            LIMIT 10
            """
        )
        rows = cursor.fetchall() or []

        recent_stories: list[dict[str, Any]] = []
        for story_id, is_published, critique_status, updated_at, synth_metadata in rows:
            meta: dict[str, Any] = {}
            if isinstance(synth_metadata, dict):
                meta = synth_metadata
            elif isinstance(synth_metadata, str) and synth_metadata.strip():
                try:
                    parsed = json.loads(synth_metadata)
                    if isinstance(parsed, dict):
                        meta = parsed
                except Exception:
                    meta = {}

            publication = meta.get("publication") if isinstance(meta.get("publication"), dict) else {}
            recent_stories.append(
                {
                    "story_id": story_id,
                    "is_published": bool(is_published),
                    "critique_status": critique_status,
                    "updated_at": str(updated_at),
                    "publication_lane": publication.get("publication_lane"),
                    "confidence_tier": publication.get("confidence_tier"),
                    "reason_codes": publication.get("decision_reason_codes"),
                    "provenance_trace_id": publication.get("provenance_trace_id"),
                }
            )

        cursor.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM articles WHERE analyzed = 0) AS unanalyzed_count,
              (SELECT COUNT(*) FROM articles WHERE analyzed = 1 AND embedded = 0) AS unembedded_count,
              (SELECT COUNT(*) FROM articles WHERE analyzed = 1 AND fact_check_status IS NULL) AS unfactchecked_count,
              (SELECT COUNT(*) FROM synthesized_articles WHERE is_published = 0 AND (critique_status IS NULL OR critique_status = 'pending')) AS pending_critique_count,
              (SELECT COUNT(*) FROM synthesized_articles WHERE is_published = 0 AND critique_status = 'completed') AS ready_to_publish_count
            """
        )
        queue_row = cursor.fetchone()
        if queue_row:
            snapshot["queue_counts"] = {
                "unanalyzed_count": int(queue_row[0] or 0),
                "unembedded_count": int(queue_row[1] or 0),
                "unfactchecked_count": int(queue_row[2] or 0),
                "pending_critique_count": int(queue_row[3] or 0),
                "ready_to_publish_count": int(queue_row[4] or 0),
            }
        snapshot["recent_stories"] = recent_stories
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            db_service.close()
        except Exception:
            pass

    return snapshot


async def _run_policy_chain(args: argparse.Namespace) -> list[PolicyResult]:
    policy_classes = [
        IngestionToAnalysisPolicy,
        AnalysisToEmbeddingPolicy,
        AnalysisToFactCheckPolicy,
        IncrementalClusteringPolicy,
        ClusterToSynthesisPolicy,
        SynthesisToCritiquePolicy,
        SynthesisToPublishingPolicy,
    ]

    results: list[PolicyResult] = []
    for policy_cls in policy_classes:
        policy = policy_cls(args.mcp_bus_url)
        name = policy.name()

        try:
            items = policy.check_condition(limit=max(args.limit, 1))
        except Exception as exc:
            results.append(
                PolicyResult(
                    name=name,
                    found_items=0,
                    sampled_items=[],
                    executed=False,
                    execution_error=f"check_condition failed: {exc}",
                )
            )
            continue

        sampled = list(items[: min(5, len(items))])
        if not args.execute or not items:
            results.append(
                PolicyResult(
                    name=name,
                    found_items=len(items),
                    sampled_items=sampled,
                    executed=False,
                )
            )
            await asyncio.sleep(max(args.sleep_seconds, 0.0))
            continue

        execution_error = None
        try:
            await policy.execute(items)
        except Exception as exc:
            execution_error = str(exc)

        results.append(
            PolicyResult(
                name=name,
                found_items=len(items),
                sampled_items=sampled,
                executed=True,
                execution_error=execution_error,
            )
        )
        await asyncio.sleep(max(args.sleep_seconds, 0.0))

    return results


def _summarize(readiness: dict[str, Any], policy_results: list[PolicyResult]) -> dict[str, Any]:
    has_execution_errors = any(p.execution_error for p in policy_results)
    published_with_lane = any(
        row.get("is_published") and row.get("publication_lane") in {"verified_story", "developing_brief"}
        for row in readiness.get("recent_stories", [])
    )

    overall_status = "ok"
    if has_execution_errors:
        overall_status = "error"
    elif not published_with_lane:
        overall_status = "warning"

    return {
        "status": overall_status,
        "published_with_lane_detected": published_with_lane,
        "has_execution_errors": has_execution_errors,
        "notes": [
            "warning indicates no recently published lane-tagged story was observed in the sampled rows",
            "error indicates at least one policy check/execute raised an exception",
        ],
    }


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Refactor E2E Smoke Report")
    lines.append("")
    lines.append(f"Generated: {report.get('generated_at')}")
    lines.append(f"Mode: {'execute' if report.get('execute') else 'check-only'}")
    lines.append(f"Overall status: {report.get('summary', {}).get('status')}")
    lines.append("")

    lines.append("## Policy Chain")
    for item in report.get("policy_results", []):
        lines.append(
            f"- {item.get('name')}: found={item.get('found_items')} executed={item.get('executed')} error={item.get('execution_error')}"
        )
    lines.append("")

    queue_counts = report.get("state", {}).get("queue_counts") or {}
    lines.append("## Queue Snapshot")
    for key, value in queue_counts.items():
        lines.append(f"- {key}: {value}")
    lines.append("")

    lines.append("## Recent Stories (top 10)")
    for row in report.get("state", {}).get("recent_stories", []):
        lines.append(
            "- "
            + f"story_id={row.get('story_id')} published={row.get('is_published')} "
            + f"lane={row.get('publication_lane')} critique_status={row.get('critique_status')} "
            + f"provenance_trace_id={row.get('provenance_trace_id')}"
        )
    lines.append("")

    lines.append("## Summary")
    summary = report.get("summary", {})
    lines.append(f"- published_with_lane_detected: {summary.get('published_with_lane_detected')}")
    lines.append(f"- has_execution_errors: {summary.get('has_execution_errors')}")
    for note in summary.get("notes", []):
        lines.append(f"- note: {note}")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()

    policy_results = asyncio.run(_run_policy_chain(args))
    state_snapshot = _load_recent_state()

    report = {
        "generated_at": _utc_now(),
        "execute": bool(args.execute),
        "mcp_bus_url": args.mcp_bus_url,
        "limit": int(args.limit),
        "policy_results": [vars(result) for result in policy_results],
        "state": state_snapshot,
    }
    report["summary"] = _summarize(report["state"], policy_results)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"refactor_e2e_smoke_{'execute' if args.execute else 'check'}_{stamp}"
    json_path = out_dir / f"{base_name}.json"
    md_path = out_dir / f"{base_name}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(_build_markdown(report))

    print(json.dumps({"status": report["summary"]["status"], "json_out": str(json_path), "md_out": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
