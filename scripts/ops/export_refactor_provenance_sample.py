#!/usr/bin/env python3
"""Export provenance sample evidence for multi-source refactor M2 parity checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("JUSTNEWS_DB_EMBEDDING_ENABLED", "0")

from database.utils.migrated_database_utils import create_database_service

REQUIRED_FIELDS = [
    "publication_lane",
    "source_count",
    "unique_domain_count",
    "confidence_tier",
    "provenance_trace_id",
    "decision_reason_codes",
    "policy_version",
    "policy_enabled",
    "policy_thresholds",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export M2 provenance sample evidence")
    parser.add_argument(
        "--env-tag",
        default="dev",
        help="Environment tag for the exported evidence (for example dev, staging)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Maximum number of recent published records to inspect",
    )
    parser.add_argument(
        "--out-dir",
        default="logs/operations/refactor_parity",
        help="Output directory for JSON and Markdown artifacts",
    )
    parser.add_argument(
        "--selection-method",
        default="most-recent-published",
        help="Selection method note written to the artifact",
    )
    return parser.parse_args()


def _safe_json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _fetch_records(sample_size: int) -> list[dict[str, Any]]:
    db_service = create_database_service()
    db_service.ensure_conn()
    if db_service.mb_conn is None:
        raise RuntimeError("MariaDB connection is not available")
    cursor = db_service.mb_conn.cursor()

    try:
        cursor.execute(
            """
            SELECT story_id, updated_at, synth_metadata
            FROM synthesized_articles
            WHERE is_published = 1
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (max(sample_size, 1),),
        )
        rows = cursor.fetchall() or []
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            db_service.close()
        except Exception:
            pass

    records: list[dict[str, Any]] = []
    for story_id, updated_at, synth_metadata in rows:
        meta = _safe_json_loads(synth_metadata)
        publication = meta.get("publication") if isinstance(meta.get("publication"), dict) else {}
        records.append(
            {
                "record_id": story_id,
                "updated_at": str(updated_at),
                "publication": publication,
            }
        )
    return records


def _normalize_reason_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _build_sample_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in records:
        publication = item.get("publication") or {}
        reason_codes = _normalize_reason_codes(publication.get("decision_reason_codes"))

        row = {
            "record_id": item.get("record_id"),
            "updated_at": item.get("updated_at"),
            "publication_lane": publication.get("publication_lane"),
            "source_count": publication.get("source_count"),
            "unique_domain_count": publication.get("unique_domain_count"),
            "confidence_tier": publication.get("confidence_tier"),
            "provenance_trace_id": publication.get("provenance_trace_id"),
            "decision_reason_codes": reason_codes,
            "policy_version": publication.get("policy_version"),
            "policy_enabled": publication.get("policy_enabled"),
            "policy_thresholds": publication.get("policy_thresholds"),
        }

        missing_fields = [field for field in REQUIRED_FIELDS if not _is_present(row.get(field))]
        row["pass"] = len(missing_fields) == 0
        row["missing_fields"] = missing_fields
        rows.append(row)

    return rows


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Multi-Source Refactor - Provenance Sample Evidence")
    lines.append("")
    lines.append(f"Date: {report['generated_at']}")
    lines.append(f"Environment: {report['env_tag']}")
    lines.append("Owner: Ops/QA")
    lines.append("")

    lines.append("## 1) Sample Set Definition")
    lines.append(f"- Query/source used: {report['query_source']}")
    lines.append(f"- Time window: {report['time_window']}")
    lines.append(f"- Sample size: {report['sample_size']}")
    lines.append(f"- Selection method: {report['selection_method']}")
    lines.append("")

    lines.append("## 2) Required Fields Checklist")
    for field in REQUIRED_FIELDS:
        lines.append(f"- {field}")
    lines.append("")

    lines.append("## 3) Record-by-Record Evidence")
    lines.append("| Record ID | publication_lane | source_count | unique_domain_count | confidence_tier | provenance_trace_id | reason_codes | policy_version | policy_enabled | policy_thresholds | Pass/Fail | Notes |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")

    for row in report["rows"]:
        reason_codes = ",".join(row["decision_reason_codes"]) if row["decision_reason_codes"] else ""
        notes = "missing: " + ", ".join(row["missing_fields"]) if row["missing_fields"] else "ok"
        thresholds = row["policy_thresholds"]
        threshold_text = json.dumps(thresholds, sort_keys=True) if isinstance(thresholds, dict) else str(thresholds)
        pass_fail = "pass" if row["pass"] else "fail"
        lines.append(
            f"| {row['record_id']} | {row['publication_lane']} | {row['source_count']} | {row['unique_domain_count']} | "
            f"{row['confidence_tier']} | {row['provenance_trace_id']} | {reason_codes} | {row['policy_version']} | "
            f"{row['policy_enabled']} | {threshold_text} | {pass_fail} | {notes} |"
        )
    lines.append("")

    lines.append("## 4) Raw Sample Artifact")
    lines.append("```json")
    lines.append(json.dumps(report["rows"], indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    summary = report["summary"]
    lines.append("## 5) Aggregated Summary")
    lines.append(f"- Total sampled: {summary['total_sampled']}")
    lines.append(f"- Complete/valid: {summary['complete_valid']}")
    lines.append(f"- Incomplete/invalid: {summary['incomplete_invalid']}")
    lines.append(f"- Completeness rate: {summary['completeness_rate_percent']:.2f}%")
    lines.append("- Target threshold: 100% for new records in M2 gate checks")
    lines.append("")

    lines.append("## 6) Exceptions and Remediation")
    if summary["incomplete_invalid"] == 0:
        lines.append("- Exception IDs: none")
        lines.append("- Root-cause notes: n/a")
        lines.append("- Remediation owner: n/a")
        lines.append("- ETA: n/a")
    else:
        failing_ids = [str(row["record_id"]) for row in report["rows"] if not row["pass"]]
        lines.append(f"- Exception IDs: {', '.join(failing_ids)}")
        lines.append("- Root-cause notes: Missing required provenance/publication fields in sampled records")
        lines.append("- Remediation owner: Data/Eng")
        lines.append("- ETA: pending triage")
    lines.append("")

    lines.append("## 7) Sign-off")
    decision = "pass" if summary["incomplete_invalid"] == 0 else "conditional"
    lines.append("- Reviewer: Ops/QA")
    lines.append(f"- Decision: {decision}")
    lines.append(f"- Timestamp (UTC): {report['generated_at']}")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = _parse_args()
    records = _fetch_records(args.sample_size)
    rows = _build_sample_rows(records)

    timestamps = [row.get("updated_at") for row in rows if row.get("updated_at")]
    time_window = "n/a"
    if timestamps:
        time_window = f"{timestamps[-1]} to {timestamps[0]}"

    total = len(rows)
    complete = sum(1 for row in rows if row["pass"])
    incomplete = total - complete
    completeness = (complete / total * 100.0) if total else 0.0

    generated_at = _utc_now_iso()
    report = {
        "generated_at": generated_at,
        "env_tag": args.env_tag,
        "query_source": "SELECT story_id, updated_at, synth_metadata FROM synthesized_articles WHERE is_published = 1 ORDER BY updated_at DESC LIMIT N",
        "time_window": time_window,
        "sample_size": total,
        "selection_method": args.selection_method,
        "rows": rows,
        "summary": {
            "total_sampled": total,
            "complete_valid": complete,
            "incomplete_invalid": incomplete,
            "completeness_rate_percent": completeness,
        },
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"multi_source_refactor_provenance_{args.env_tag}_{stamp}"
    json_path = out_dir / f"{base_name}.json"
    md_path = out_dir / f"{base_name}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(_build_markdown(report))

    print(
        json.dumps(
            {
                "status": "ok",
                "env_tag": args.env_tag,
                "sample_size": total,
                "complete_valid": complete,
                "incomplete_invalid": incomplete,
                "json_out": str(json_path),
                "md_out": str(md_path),
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
