#!/usr/bin/env python3
"""Capture Multi-Source refactor parity artifacts from a target orchestrator.

This helper is intended for dev/staging parity follow-up after current-purpose
approval. It captures runtime-config snapshots, metrics evidence lines, and can
optionally execute a rollback drill (apply -> rollback) when explicitly enabled.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


METRIC_PATTERN = re.compile(
    r"published_verified_share|published_total_|cluster_promotion_failures|singleton_to_verified_conversion"
)


@dataclass
class ApiResult:
    endpoint: str
    status_code: int
    ok: bool
    duration_seconds: float
    payload: dict[str, Any] | None = None
    error: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _request_json(
    method: str,
    url: str,
    *,
    timeout: float,
    json_payload: dict[str, Any] | None = None,
) -> ApiResult:
    started = time.monotonic()
    try:
        response = requests.request(method, url, json=json_payload, timeout=timeout)
        duration = time.monotonic() - started
        payload: dict[str, Any] | None = None
        if response.headers.get("content-type", "").lower().startswith("application/json"):
            try:
                parsed = response.json()
                payload = parsed if isinstance(parsed, dict) else {"data": parsed}
            except Exception as exc:  # pragma: no cover - malformed json edge
                payload = {"parse_error": str(exc)}
        return ApiResult(
            endpoint=url,
            status_code=response.status_code,
            ok=response.ok,
            duration_seconds=round(duration, 6),
            payload=payload,
        )
    except Exception as exc:
        duration = time.monotonic() - started
        return ApiResult(
            endpoint=url,
            status_code=0,
            ok=False,
            duration_seconds=round(duration, 6),
            error=str(exc),
        )


def _request_text(url: str, *, timeout: float) -> tuple[ApiResult, str]:
    started = time.monotonic()
    try:
        response = requests.get(url, timeout=timeout)
        duration = time.monotonic() - started
        return (
            ApiResult(
                endpoint=url,
                status_code=response.status_code,
                ok=response.ok,
                duration_seconds=round(duration, 6),
            ),
            response.text,
        )
    except Exception as exc:
        duration = time.monotonic() - started
        return (
            ApiResult(
                endpoint=url,
                status_code=0,
                ok=False,
                duration_seconds=round(duration, 6),
                error=str(exc),
            ),
            "",
        )


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Multi-Source Refactor Parity Artifact Capture")
    lines.append("")
    lines.append(f"Generated: {report.get('generated_at')}")
    lines.append(f"Environment tag: {report.get('env_tag')}")
    lines.append(f"Orchestrator URL: {report.get('orch_url')}")
    lines.append("")

    lines.append("## Runtime Config Snapshots")
    runtime = report.get("runtime_config", {})
    before = runtime.get("before") or {}
    after = runtime.get("after") or {}
    lines.append(f"- before status: {before.get('status_code')} (ok={before.get('ok')})")
    lines.append(f"- after status: {after.get('status_code')} (ok={after.get('ok')})")
    lines.append("")

    lines.append("## Metrics Evidence")
    metrics = report.get("metrics", {})
    lines.append(f"- status: {metrics.get('status_code')} (ok={metrics.get('ok')})")
    interesting = metrics.get("interesting_lines") or []
    lines.append(f"- matched lines: {len(interesting)}")
    for line in interesting[:20]:
        lines.append(f"  - `{line}`")
    lines.append("")

    rollback = report.get("rollback_drill") or {}
    lines.append("## Rollback Drill")
    lines.append(f"- enabled: {rollback.get('enabled', False)}")
    if rollback.get("enabled"):
        lines.append(
            f"- apply status: {(rollback.get('apply') or {}).get('status_code')} (ok={(rollback.get('apply') or {}).get('ok')})"
        )
        lines.append(
            f"- rollback status: {(rollback.get('rollback') or {}).get('status_code')} (ok={(rollback.get('rollback') or {}).get('ok')})"
        )
    lines.append("")

    lines.append("## Dashboard/Alert Attachments")
    lines.append(f"- dashboard URLs: {report.get('dashboard_urls') or []}")
    lines.append(f"- panel IDs: {report.get('panel_ids') or []}")
    lines.append(f"- alert IDs: {report.get('alert_ids') or []}")
    lines.append(f"- screenshot links: {report.get('screenshot_links') or []}")
    lines.append("")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture refactor parity artifacts from orchestrator")
    parser.add_argument("--orch-url", required=True, help="Base URL for workflow orchestrator")
    parser.add_argument("--env-tag", required=True, help="Environment tag, e.g. dev or staging")
    parser.add_argument(
        "--out-dir",
        default="logs/operations/refactor_parity",
        help="Output directory for generated JSON/Markdown artifacts",
    )
    parser.add_argument("--request-timeout", type=float, default=10.0, help="HTTP request timeout (seconds)")
    parser.add_argument(
        "--run-rollback-drill",
        action="store_true",
        help="Execute runtime apply+rollback calls (disabled by default)",
    )
    parser.add_argument(
        "--rollback-target-version",
        type=int,
        default=0,
        help="Target version for rollback call when rollback drill is enabled",
    )
    parser.add_argument(
        "--dashboard-url",
        action="append",
        default=[],
        help="Dashboard URL(s) to include in artifact (repeat flag for multiple)",
    )
    parser.add_argument(
        "--panel-id",
        action="append",
        default=[],
        help="Panel IDs to include (repeat flag for multiple)",
    )
    parser.add_argument(
        "--alert-id",
        action="append",
        default=[],
        help="Alert rule IDs to include (repeat flag for multiple)",
    )
    parser.add_argument(
        "--screenshot-link",
        action="append",
        default=[],
        help="Screenshot/export artifact links (repeat flag for multiple)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    orch_url = args.orch_url.rstrip("/")
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"multi_source_refactor_{args.env_tag}_{stamp}"

    runtime_before = _request_json("GET", f"{orch_url}/runtime-config", timeout=args.request_timeout)
    metrics_meta, metrics_text = _request_text(f"{orch_url}/metrics", timeout=args.request_timeout)
    interesting_lines = [line for line in metrics_text.splitlines() if METRIC_PATTERN.search(line)]

    rollback_section: dict[str, Any] = {"enabled": bool(args.run_rollback_drill)}
    if args.run_rollback_drill:
        apply_payload = {
            "patch": {
                "orchestrator.lane_policy.enabled": True,
                "orchestrator.lane_policy.topic_overrides_json": '{"breaking":{"min_article_count":1,"min_source_count":1,"min_unique_domains":1}}',
            },
            "reason": f"parity capture apply ({args.env_tag})",
            "actor": "ops",
        }
        rollback_payload = {
            "target_version": int(args.rollback_target_version),
            "reason": f"parity capture rollback ({args.env_tag})",
            "actor": "ops",
        }
        apply_result = _request_json(
            "PATCH",
            f"{orch_url}/runtime-config",
            timeout=args.request_timeout,
            json_payload=apply_payload,
        )
        rollback_result = _request_json(
            "POST",
            f"{orch_url}/runtime-config/rollback",
            timeout=args.request_timeout,
            json_payload=rollback_payload,
        )
        rollback_section.update(
            {
                "apply_payload": apply_payload,
                "rollback_payload": rollback_payload,
                "apply": asdict(apply_result),
                "rollback": asdict(rollback_result),
            }
        )

    runtime_after = _request_json("GET", f"{orch_url}/runtime-config", timeout=args.request_timeout)

    report: dict[str, Any] = {
        "generated_at": _utc_now(),
        "env_tag": args.env_tag,
        "orch_url": orch_url,
        "runtime_config": {
            "before": asdict(runtime_before),
            "after": asdict(runtime_after),
        },
        "metrics": {
            **asdict(metrics_meta),
            "interesting_lines": interesting_lines,
        },
        "rollback_drill": rollback_section,
        "dashboard_urls": args.dashboard_url,
        "panel_ids": args.panel_id,
        "alert_ids": args.alert_id,
        "screenshot_links": args.screenshot_link,
    }

    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)

    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(_build_markdown(report))

    print(json.dumps({"json_out": str(json_path), "md_out": str(md_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
