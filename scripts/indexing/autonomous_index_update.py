#!/usr/bin/env python3
"""Autonomous updater for local code index.

Designed for periodic execution via systemd user timer.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh local code index")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--index-dir",
        default=".cache/code_index",
        help="Directory containing index artifacts",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full rebuild instead of incremental refresh",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print underlying indexer command",
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


def main() -> int:
    started = time.perf_counter()
    args = parse_args()
    root = Path(args.root).resolve()

    command = [
        "python3",
        "scripts/indexing/build_code_index.py",
        "--root",
        str(root),
        "--index-dir",
        str(args.index_dir),
    ]
    if args.full:
        command.append("--full")
    if args.verbose:
        command.append("--verbose")
        print("running:", " ".join(command))

    completed = subprocess.run(command, cwd=root)
    exit_code = int(completed.returncode)

    if not args.no_telemetry:
        try:
            _append_telemetry(
                root,
                args.telemetry_path,
                {
                    "event_type": "index_autoupdate",
                    "mode": "full" if args.full else "incremental",
                    "exit_code": exit_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
                },
            )
        except Exception:
            # Telemetry must never fail updater execution.
            pass

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
