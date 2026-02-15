#!/usr/bin/env python3
"""Generate a Living Story operator report from synthesized metadata.

This script is a lightweight dashboard artifact for Phase-3 operational visibility.
It summarizes decision telemetry, override usage, and publish latency trends from
`synthesized_articles.synth_metadata`.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

try:
    import mysql.connector
except Exception:  # pragma: no cover
    mysql = None


@dataclass
class StoryTelemetry:
    story_id: str
    cluster_id: str
    action: str
    meaningful_score: float
    composite_score: float
    urgency_class: str
    calibration_profile: str
    decision_counts: dict[str, int]
    publish_latency_mean: float | None
    override_used: bool
    override_rejected: bool


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _parse_story_row(row: tuple[Any, ...]) -> StoryTelemetry | None:
    story_id, cluster_id, raw_meta = row
    root = _safe_dict(raw_meta)
    living = root.get("living_story") if isinstance(root.get("living_story"), dict) else {}
    if not living:
        return None

    explain = living.get("explainability") if isinstance(living.get("explainability"), dict) else {}
    telemetry = living.get("telemetry") if isinstance(living.get("telemetry"), dict) else {}

    override_obj = explain.get("override")
    override_rejected = explain.get("override_rejected")

    return StoryTelemetry(
        story_id=str(story_id),
        cluster_id=str(cluster_id),
        action=str(living.get("last_update_action", "unknown")),
        meaningful_score=_safe_float(living.get("last_meaningful_score"), 0.0),
        composite_score=_safe_float(living.get("last_composite_score"), 0.0),
        urgency_class=str(explain.get("urgency_class", "unknown")),
        calibration_profile=str(explain.get("calibration_profile", "unknown")),
        decision_counts={k: int(v) for k, v in dict(telemetry.get("decision_counts") or {}).items()},
        publish_latency_mean=_safe_float(telemetry.get("mean_publish_latency_seconds"), None)
        if telemetry.get("mean_publish_latency_seconds") is not None
        else None,
        override_used=isinstance(override_obj, dict) and bool(override_obj),
        override_rejected=isinstance(override_rejected, dict) and bool(override_rejected),
    )


def _connect_db():
    if mysql is None:  # pragma: no cover
        raise RuntimeError("mysql.connector is not available in this environment")

    return mysql.connector.connect(
        user=os.environ.get("MARIADB_USER", "justnews"),
        password=os.environ.get("MARIADB_PASSWORD", "dev_justnews_password"),
        host=os.environ.get("MARIADB_HOST", "127.0.0.1"),
        port=int(os.environ.get("MARIADB_PORT", 3306)),
        database=os.environ.get("MARIADB_DB", "justnews"),
        autocommit=True,
        use_pure=True,
    )


def build_report(limit: int) -> dict[str, Any]:
    with _connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT story_id, cluster_id, synth_metadata
                FROM synthesized_articles
                WHERE synth_metadata IS NOT NULL
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()

    stories = [item for item in (_parse_story_row(r) for r in rows) if item]

    actions: dict[str, int] = {}
    urgency: dict[str, int] = {}
    profiles: dict[str, int] = {}
    latencies: list[float] = []
    meaningful_scores: list[float] = []
    composite_scores: list[float] = []

    for story in stories:
        actions[story.action] = actions.get(story.action, 0) + 1
        urgency[story.urgency_class] = urgency.get(story.urgency_class, 0) + 1
        profiles[story.calibration_profile] = profiles.get(story.calibration_profile, 0) + 1
        meaningful_scores.append(story.meaningful_score)
        composite_scores.append(story.composite_score)
        if story.publish_latency_mean is not None:
            latencies.append(story.publish_latency_mean)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_size": len(stories),
        "actions": actions,
        "urgency_classes": urgency,
        "calibration_profiles": profiles,
        "override_usage": {
            "used": sum(1 for s in stories if s.override_used),
            "rejected": sum(1 for s in stories if s.override_rejected),
        },
        "scores": {
            "meaningful_mean": round(mean(meaningful_scores), 4) if meaningful_scores else 0.0,
            "meaningful_median": round(median(meaningful_scores), 4) if meaningful_scores else 0.0,
            "composite_mean": round(mean(composite_scores), 4) if composite_scores else 0.0,
            "composite_median": round(median(composite_scores), 4) if composite_scores else 0.0,
        },
        "publish_latency_seconds": {
            "mean": round(mean(latencies), 2) if latencies else None,
            "median": round(median(latencies), 2) if latencies else None,
        },
        "top_recent": [
            {
                "story_id": s.story_id,
                "cluster_id": s.cluster_id,
                "action": s.action,
                "composite_score": s.composite_score,
                "urgency_class": s.urgency_class,
                "calibration_profile": s.calibration_profile,
                "override_used": s.override_used,
                "override_rejected": s.override_rejected,
            }
            for s in stories[:10]
        ],
    }
    return report


def _to_markdown(report: dict[str, Any]) -> str:
    lines = []
    lines.append("# Living Story Dashboard Report")
    lines.append("")
    lines.append(f"Generated: {report.get('generated_at')}")
    lines.append(f"Sample size: {report.get('sample_size')}")
    lines.append("")
    lines.append("## Actions")
    for key, value in sorted((report.get("actions") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Urgency Classes")
    for key, value in sorted((report.get("urgency_classes") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Calibration Profiles")
    for key, value in sorted((report.get("calibration_profiles") or {}).items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Score Summary")
    score = report.get("scores") or {}
    lines.append(f"- meaningful mean: {score.get('meaningful_mean')}")
    lines.append(f"- meaningful median: {score.get('meaningful_median')}")
    lines.append(f"- composite mean: {score.get('composite_mean')}")
    lines.append(f"- composite median: {score.get('composite_median')}")
    lines.append("")
    latency = report.get("publish_latency_seconds") or {}
    lines.append("## Publish Latency")
    lines.append(f"- mean seconds: {latency.get('mean')}")
    lines.append(f"- median seconds: {latency.get('median')}")
    lines.append("")
    lines.append("## Override Usage")
    override = report.get("override_usage") or {}
    lines.append(f"- used: {override.get('used', 0)}")
    lines.append(f"- rejected: {override.get('rejected', 0)}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Living Story telemetry dashboard report")
    parser.add_argument("--limit", type=int, default=500, help="Max stories to include in sample")
    parser.add_argument("--json-out", default="", help="Optional path to write JSON output")
    parser.add_argument("--md-out", default="", help="Optional path to write Markdown output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(limit=max(args.limit, 1))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    md = _to_markdown(report)
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as f:
            f.write(md + "\n")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
