#!/usr/bin/env python3
"""GPU activity monitor

Monitors GPU utilization and automatically starts/stops telemetry collectors
when the GPU is actively under load. This avoids missing telemetry during
ad-hoc model inference runs or other bursts.

Behavior:
- Polls GPU utilization at a configurable interval.
- If average utilization over 'window' seconds exceeds --start-threshold (%),
  it starts the telemetry CSV collector and optional Prometheus exporter.
- If utilization falls below --stop-threshold for 'idle' seconds it stops them.

Usage:
  python3 scripts/perf/gpu_activity_monitor.py --start-threshold 20 --stop-threshold 10

This script manages PID files under /tmp/gpu_telemetry.* so it can be run
by the orchestrator or as a standalone background service.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from collections import deque


def run_cmd(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8")
    except Exception:
        return ""


def get_gpu_util() -> float | None:
    # Try NVML via nvidia-smi
    out = run_cmd(
        ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
    )
    if out:
        try:
            # handle multiple GPUs - take max util across GPUs
            vals = [float(x.strip()) for x in out.splitlines() if x.strip()]
            if vals:
                return max(vals)
        except Exception:
            return None
    return None


def start_telemetry(
    out_dir: str, bnb_version: str | None = None, exporter_port: int | None = None
):
    # start telemetry script (shell), store pid
    telem_pid_file = "/tmp/gpu_telemetry.pid"
    exporter_pid_file = "/tmp/gpu_telemetry_exporter.pid"

    if not os.path.exists(telem_pid_file):
        cmd = [os.path.join("scripts", "perf", "gpu_telemetry.sh"), out_dir]
        # start in background
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(telem_pid_file, "w") as f:
            f.write(str(p.pid))
        print("started gpu_telemetry.sh pid", p.pid)

    if exporter_port and not os.path.exists(exporter_pid_file):
        # Use the canonical project conda environment name for running monitoring helpers
        conda_env = os.environ.get("CANONICAL_ENV", "justnews-py312")
        cmd = [
            "mamba",
            "run",
            "-n",
            conda_env,
            "python",
            os.path.join("scripts", "perf", "gpu_telemetry_exporter.py"),
            "--port",
            str(exporter_port),
            "--interval",
            "1",
        ]
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(exporter_pid_file, "w") as f:
            f.write(str(p.pid))
        print("started exporter pid", p.pid)


def stop_telemetry():
    telem_pid_file = "/tmp/gpu_telemetry.pid"
    exporter_pid_file = "/tmp/gpu_telemetry_exporter.pid"

    def kill_pidfile(pfile):
        if os.path.exists(pfile):
            try:
                pid = int(open(pfile).read().strip())
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
            try:
                os.remove(pfile)
            except Exception:
                pass

    kill_pidfile(telem_pid_file)
    kill_pidfile(exporter_pid_file)
    # best-effort: kill any lingering spinner processes
    run_cmd(["pkill", "-f", "gpu_telemetry.sh"])
    run_cmd(["pkill", "-f", "gpu_telemetry_exporter.py"])
    print("telemetry stopped (pid files removed)")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument(
        "--start-threshold",
        type=float,
        default=20.0,
        help="percent util to start telemetry",
    )
    p.add_argument(
        "--stop-threshold",
        type=float,
        default=10.0,
        help="percent util below which to stop",
    )
    p.add_argument(
        "--window", type=int, default=5, help="seconds sliding window for smoothing"
    )
    p.add_argument(
        "--idle",
        type=int,
        default=10,
        help="seconds below stop-threshold before stopping",
    )
    p.add_argument("--out-dir", type=str, default="/var/log/justnews-perf")
    p.add_argument("--exporter-port", type=int, default=9118)
    p.add_argument("--poll-seconds", type=float, default=1.0)
    args = p.parse_args(argv)

    # sliding average buffer
    buf = deque(maxlen=max(1, int(args.window / max(1, args.poll_seconds))))
    active = False
    idle_counter = 0

    print(
        f"starting GPU activity monitor (start>={args.start_threshold:.1f}% stop<={args.stop_threshold:.1f}% window={args.window}s idle={args.idle}s)"
    )
    try:
        while True:
            util = get_gpu_util()
            if util is None:
                # if no GPU / nvidia-smi fails, clear buffer and sleep
                buf.clear()
                time.sleep(args.poll_seconds)
                continue

            buf.append(util)
            avg = sum(buf) / len(buf)

            if not active and avg >= args.start_threshold:
                print(f"activity detected avg util={avg:.1f}% - starting telemetry")
                os.makedirs(args.out_dir, exist_ok=True)
                start_telemetry(args.out_dir, exporter_port=args.exporter_port)
                active = True
                idle_counter = 0
            elif active:
                if avg <= args.stop_threshold:
                    idle_counter += args.poll_seconds
                    if idle_counter >= args.idle:
                        print(f"idle detected avg util={avg:.1f}% - stopping telemetry")
                        stop_telemetry()
                        active = False
                        idle_counter = 0
                else:
                    idle_counter = 0

            time.sleep(args.poll_seconds)

    except KeyboardInterrupt:
        print("stopping monitor")
        stop_telemetry()


if __name__ == "__main__":
    main()
