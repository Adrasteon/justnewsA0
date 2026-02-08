#!/usr/bin/env python3
"""GPU activity monitor agent

Monitors GPU utilization and will automatically start/stop the telemetry
collector (`gpu_telemetry.sh`) and the Prometheus exporter
(`gpu_telemetry_exporter.py`) while the GPU is active.

This is intentionally small and dependency-free (uses subprocess + nvidia-smi).

Key behaviour:
 - When GPU utilization >= --start-util for at least --start-seconds, start telemetry and exporter.
 - When GPU utilization stays <= --stop-util for at least --stop-seconds, stop telemetry and exporter.

This makes telemetry capture automatic during real model runs without requiring human action.

Usage examples:
  # Monitor GPU and start telemetry when util >= 20% for 5 seconds and stop when <= 10% for 10s
  python3 scripts/perf/gpu_activity_agent.py --start-util 20 --start-seconds 5 --stop-util 10 --stop-seconds 10

Test mode:
  --test will simulate a load spike to exercise start/stop without actually stressing the GPU.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import time

PID_TELEMETRY = "/tmp/gpu_telemetry.pid"
PID_EXPORTER = "/tmp/gpu_telemetry_exporter.pid"


def run_cmd(cmd, capture=False):
    if capture:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return out.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    else:
        return subprocess.call(cmd)


def get_gpu_util() -> float | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=1.0,
        )
        s = out.decode("utf-8", errors="ignore").strip().splitlines()[0].strip()
        return float(s) if s else None
    except Exception:
        return None


def is_running(pidfile: str) -> bool:
    if not os.path.exists(pidfile):
        return False
    try:
        with open(pidfile) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        try:
            os.remove(pidfile)
        except Exception:
            pass
        return False


def start_telemetry(out_dir="/var/log/justnews-perf") -> None:
    if is_running(PID_TELEMETRY):
        print("telemetry already running")
        return
    os.makedirs(out_dir, exist_ok=True)
    cmd = f"nohup ./scripts/perf/gpu_telemetry.sh {shlex.quote(out_dir)} > {shlex.quote(out_dir)}/gpu_telemetry_launcher.log 2>&1 & echo $!"
    pid = run_cmd(["bash", "-lc", cmd], capture=True).strip()
    if pid:
        with open(PID_TELEMETRY, "w") as f:
            f.write(pid)
        print("started telemetry pid", pid)


def stop_telemetry() -> None:
    if not os.path.exists(PID_TELEMETRY):
        print("telemetry not running")
        return
    try:
        with open(PID_TELEMETRY) as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            os.kill(pid, 9)
        except Exception:
            pass
    except Exception:
        pass
    try:
        os.remove(PID_TELEMETRY)
    except Exception:
        pass
    print("stopped telemetry")


def start_exporter(port=9118, interval=1.0):
    if is_running(PID_EXPORTER):
        print("exporter already running")
        return
    # prefer a configured python interpreter (set via service env /etc/default)
    py = os.environ.get("JN_PYTHON_BIN") or os.environ.get("PYTHON_BIN") or "python3"
    cmd = f"nohup {py} scripts/perf/gpu_telemetry_exporter.py --port {int(port)} --interval {float(interval)} > /var/log/justnews-perf/gpu_telemetry_exporter.log 2>&1 & echo $!"
    pid = run_cmd(["bash", "-lc", cmd], capture=True).strip()
    if pid:
        with open(PID_EXPORTER, "w") as f:
            f.write(pid)
        print("started exporter pid", pid)


def stop_exporter():
    if not os.path.exists(PID_EXPORTER):
        print("exporter not running")
        return
    try:
        with open(PID_EXPORTER) as f:
            pid = int(f.read().strip())
        os.kill(pid, 15)
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            os.kill(pid, 9)
        except Exception:
            pass
    except Exception:
        pass
    try:
        os.remove(PID_EXPORTER)
    except Exception:
        pass
    print("stopped exporter")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--start-util", type=float, default=20.0, help="GPU util %% to consider active"
    )
    p.add_argument(
        "--start-seconds",
        type=int,
        default=5,
        help="Seconds of sustained activity before starting telemetry",
    )
    p.add_argument(
        "--stop-util",
        type=float,
        default=10.0,
        help="GPU util %% threshold to consider idle",
    )
    p.add_argument(
        "--stop-seconds",
        type=int,
        default=10,
        help="Seconds of sustained idle before stopping telemetry",
    )
    p.add_argument("--out-dir", type=str, default="/var/log/justnews-perf")
    p.add_argument("--exporter-port", type=int, default=9118)
    p.add_argument("--exporter-interval", type=float, default=1.0)
    p.add_argument("--poll-interval", type=float, default=1.0)
    p.add_argument(
        "--test",
        action="store_true",
        help="Simulate a short load spike for testing start/stop behavior",
    )
    args = p.parse_args()

    active_counter = 0
    idle_counter = 0
    telemetry_active = False

    print(
        "GPU activity agent starting — polling nvidia-smi every",
        args.poll_interval,
        "s",
    )

    if args.test:
        # simulate a load spike for quick test
        print("TEST MODE: simulating load spike")
        # start telemetry immediately
        start_exporter(port=args.exporter_port, interval=args.exporter_interval)
        start_telemetry(out_dir=args.out_dir)
        print("Sleeping 5s with telemetry active (test)")
        time.sleep(5)
        stop_telemetry()
        stop_exporter()
        print("TEST finished")
        return

    try:
        while True:
            util = get_gpu_util()
            if util is None:
                # no GPU or nvidia-smi unavailable — just sleep
                time.sleep(args.poll_interval)
                continue

            # print a concise line for visibility
            print(f"gpu util={util:.1f}% (active? {telemetry_active})")

            if not telemetry_active and util >= args.start_util:
                active_counter += 1
                idle_counter = 0
            elif not telemetry_active:
                active_counter = 0

            if telemetry_active and util <= args.stop_util:
                idle_counter += 1
                active_counter = 0
            elif telemetry_active:
                idle_counter = 0

            if not telemetry_active and active_counter >= args.start_seconds:
                print("Sustained activity detected — starting telemetry + exporter")
                start_exporter(port=args.exporter_port, interval=args.exporter_interval)
                start_telemetry(out_dir=args.out_dir)
                telemetry_active = True
                active_counter = 0

            if telemetry_active and idle_counter >= args.stop_seconds:
                print("Sustained idle detected — stopping telemetry + exporter")
                stop_telemetry()
                stop_exporter()
                telemetry_active = False
                idle_counter = 0

            time.sleep(args.poll_interval)

    except KeyboardInterrupt:
        print("Interrupted — cleaning up")
        stop_telemetry()
        stop_exporter()


if __name__ == "__main__":
    main()
