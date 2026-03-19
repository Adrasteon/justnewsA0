#!/usr/bin/env python3
"""Summarize canary gate checkpoints and emit a simple GO/NO-GO verdict.

This script reads key=value checkpoint files created by /tmp/aw4_gate/snapshot.py
and computes window deltas for throughput and reliability.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def parse_kv_file(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        try:
            if "." in value:
                num = float(value)
                data[key] = int(num) if num.is_integer() else num
            else:
                data[key] = int(value)
        except Exception:
            data[key] = value
    return data


def load_checkpoint(directory: Path, label: str) -> dict[str, Any]:
    db = parse_kv_file(directory / f"{label}_db.txt")
    reliability = parse_kv_file(directory / f"{label}_reliability.txt")
    status = parse_kv_file(directory / f"{label}_status.txt")
    return {"db": db, "reliability": reliability, "status": status}


def safe_delta(end: dict[str, Any], start: dict[str, Any], key: str) -> int | None:
    if key not in end or key not in start:
        return None
    try:
        return int(end[key]) - int(start[key])
    except Exception:
        return None


def fetch_scheduler_mode(status_url: str) -> str:
    try:
        with urlopen(status_url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        signals = payload.get("signals") or {}
        scheduler = signals.get("scheduler") or {}
        return str(scheduler.get("mode") or "unknown")
    except Exception:
        return "unavailable"


def print_metric_line(name: str, value: Any) -> None:
    print(f"{name:<40} {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Canary gate scorecard")
    parser.add_argument("--dir", default="/tmp/aw4_gate", help="Checkpoint directory")
    parser.add_argument("--start", default="baseline", help="Start checkpoint label")
    parser.add_argument("--end", default="t15m", help="End checkpoint label")
    parser.add_argument(
        "--status-url",
        default="http://127.0.0.1:8023/status",
        help="Workflow orchestrator status URL",
    )
    parser.add_argument(
        "--min-analyzed-delta",
        type=int,
        default=1,
        help="Minimum analyzed increase required for GO",
    )
    parser.add_argument(
        "--min-backlog-drain",
        type=int,
        default=1,
        help="Minimum backlog drain required for GO",
    )
    parser.add_argument(
        "--max-mysql-disconnect-increase",
        type=int,
        default=0,
        help="Maximum allowed MySQL disconnect increase for GO",
    )
    parser.add_argument(
        "--max-500-increase",
        type=int,
        default=0,
        help="Maximum allowed analyst 500 marker increase for GO",
    )
    args = parser.parse_args()

    directory = Path(args.dir)
    start = load_checkpoint(directory, args.start)
    end = load_checkpoint(directory, args.end)

    if not start["db"] or not end["db"]:
        print("ERROR: missing checkpoint files. Expected *_db.txt files for start/end labels.")
        return 2

    analyzed_delta = safe_delta(end["db"], start["db"], "analyzed")
    backlog_delta = safe_delta(end["db"], start["db"], "backlog_analyzed0")
    backlog_drain = -backlog_delta if backlog_delta is not None else None
    req_delta = safe_delta(
        end["reliability"], start["reliability"], "analyst_requests_total"
    )
    mysql_delta = safe_delta(
        end["reliability"], start["reliability"], "mysql_disconnect_total"
    )
    err500_delta = safe_delta(
        end["reliability"], start["reliability"], "analyst_500_markers_total"
    )
    last60m_delta = safe_delta(end["db"], start["db"], "newly_analyzed_last60m")

    scheduler_mode = fetch_scheduler_mode(args.status_url)

    print("CANARY SCORECARD")
    print(f"window: {args.start} -> {args.end}")
    print("-" * 64)
    print_metric_line("analyzed_delta", analyzed_delta)
    print_metric_line("backlog_drain", backlog_drain)
    print_metric_line("analyst_requests_delta", req_delta)
    print_metric_line("mysql_disconnect_delta", mysql_delta)
    print_metric_line("analyst_500_delta", err500_delta)
    print_metric_line("newly_analyzed_last60m_delta", last60m_delta)
    print_metric_line("scheduler_mode_now", scheduler_mode)

    checks: list[tuple[str, bool]] = []
    if analyzed_delta is None:
        checks.append(("analyzed_delta_present", False))
    else:
        checks.append(("analyzed_delta_threshold", analyzed_delta >= args.min_analyzed_delta))

    if backlog_drain is None:
        checks.append(("backlog_drain_present", False))
    else:
        checks.append(("backlog_drain_threshold", backlog_drain >= args.min_backlog_drain))

    if mysql_delta is None:
        checks.append(("mysql_disconnect_delta_present", False))
    else:
        checks.append(
            (
                "mysql_disconnect_delta_threshold",
                mysql_delta <= args.max_mysql_disconnect_increase,
            )
        )

    if err500_delta is None:
        checks.append(("analyst_500_delta_present", False))
    else:
        checks.append(("analyst_500_delta_threshold", err500_delta <= args.max_500_increase))

    print("-" * 64)
    for name, ok in checks:
        print_metric_line(name, "PASS" if ok else "FAIL")

    verdict = "GO" if all(ok for _, ok in checks) else "NO_GO"
    print("-" * 64)
    print_metric_line("VERDICT", verdict)

    return 0 if verdict == "GO" else 1


if __name__ == "__main__":
    sys.exit(main())
