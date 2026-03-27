#!/usr/bin/env python3
"""Mini SAFE_MODE toggle demonstration

Runs orchestrator in SAFE_MODE=true then SAFE_MODE=false modes (in-process FastAPI lifespan)
and captures lease behavior + /metrics snapshots for documentation.

Outputs JSONL records under orchestrator_demo_results/.

Design:
- Use TestClient to avoid external network/server complexity
- Patch environment for SAFE_MODE before import each cycle (run in separate process if needed)
- Collect endpoints: /health, /ready, /policy (GET), /lease, /metrics
- For SAFE_MODE=true expect lease.granted False and note SAFE_MODE
- For SAFE_MODE=false expect lease.granted True (or graceful fallback if no GPU present -> granted False but no SAFE_MODE note)

Limitations:
- If actual GPUs not present, /lease may still fail to grant; script annotates outcome.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

RESULTS_DIR = Path(__file__).parent / "orchestrator_demo_results"
RESULTS_DIR.mkdir(exist_ok=True)


def _load_app():
    # Local import so SAFE_MODE env var re-evaluated
    from agents.gpu_orchestrator.main import app  # type: ignore

    return app


def run_cycle_inprocess(safe_mode: bool) -> dict[str, Any]:
    """Original in-process cycle (kept for reference / debugging)."""
    os.environ["SAFE_MODE"] = "true" if safe_mode else "false"
    app = _load_app()
    record: dict[str, Any] = {
        "safe_mode": safe_mode,
        "timestamp": datetime.now(UTC).isoformat(),
        "mode": "inprocess",
    }
    with TestClient(app) as client:
        for ep in ("health", "ready", "policy"):
            r = client.get(f"/{ep}")
            record[ep] = (
                r.json()
                if r.headers.get("content-type", "").startswith("application/json")
                else r.text
            )
        lease_req = {"agent": "demo", "memory_gb": 0.1}
        lr = client.post("/lease", json=lease_req)
        try:
            record["lease"] = lr.json()
        except Exception:
            record["lease_raw"] = lr.text
        mr = client.get("/metrics")
        record["metrics_text"] = mr.text.splitlines()[:40]
    return record


IS_SUBPROCESS = os.environ.get("SAFE_MODE_DEMO_SUBPROC") == "1"


def _subprocess_entry():  # pragma: no cover - simple runtime helper
    mode = os.environ.get("SUB_SAFE_MODE", "true").lower() == "true"
    result = run_cycle_inprocess(mode)
    print("__SAFE_MODE_DEMO_RESULT_START__")
    print(json.dumps(result))
    print("__SAFE_MODE_DEMO_RESULT_END__")


def run_cycle_subprocess(safe_mode: bool) -> dict[str, Any]:
    """Spawn a fresh interpreter so module import resets SAFE_MODE constant."""
    env = os.environ.copy()
    env["SAFE_MODE_DEMO_SUBPROC"] = "1"
    env["SUB_SAFE_MODE"] = "true" if safe_mode else "false"
    # Clear potential module import caching influences (not strictly required across process boundary)
    cmd: list[str] = [sys.executable, __file__]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
    stdout = proc.stdout.splitlines()
    collecting = False
    payload_lines: list[str] = []
    for line in stdout:
        if line.strip() == "__SAFE_MODE_DEMO_RESULT_START__":
            collecting = True
            continue
        if line.strip() == "__SAFE_MODE_DEMO_RESULT_END__":
            break
        if collecting:
            payload_lines.append(line)
    data = (
        json.loads("\n".join(payload_lines))
        if payload_lines
        else {"error": "no_payload"}
    )
    data["mode"] = "subprocess"
    return data


def main():
    cycles = []
    # Use subprocess isolation to ensure SAFE_MODE toggle is honored
    for mode in (True, False):
        start = time.time()
        rec = run_cycle_subprocess(mode)
        rec["duration_s"] = round(time.time() - start, 4)
        cycles.append(rec)
        out_path = RESULTS_DIR / f"safe_mode_cycle_{'on' if mode else 'off'}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2)
        print(f"Saved {out_path}")
    # write combined JSONL
    combined_path = RESULTS_DIR / "safe_mode_toggle.jsonl"
    with combined_path.open("w", encoding="utf-8") as f:
        for c in cycles:
            f.write(json.dumps(c) + "\n")
    print(f"Combined log written: {combined_path}")


if __name__ == "__main__":  # pragma: no cover
    if IS_SUBPROCESS:
        _subprocess_entry()
    else:
        main()
