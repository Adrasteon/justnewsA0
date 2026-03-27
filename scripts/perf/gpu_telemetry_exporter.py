#!/usr/bin/env python3
"""Small Prometheus exporter for GPU + host telemetry used by our perf tests.

This reads nvidia-smi queries and hwmon/powercap (RAPL) and exposes metrics
on /metrics using prometheus_client. It's intentionally lightweight — no
external deps beyond prometheus_client and a Python runtime.

Usage:
  # run in the project UV/.venv (or current Python)
  python3 scripts/perf/gpu_telemetry_exporter.py --port 9118 --interval 1

The exporter handles missing sensors gracefully and will report NaN for
metrics it cannot read.
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import time

from prometheus_client import Gauge, start_http_server


def run_cmd(cmd: list[str], timeout: float = 1.0) -> str:
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=timeout)
        return out.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def parse_nvidia_smi_one() -> dict:
    # Query the first GPU row - match columns to our telemetry
    cols = [
        "timestamp",
        "power.draw",
        "temperature.gpu",
        "utilization.gpu",
        "utilization.memory",
        "memory.used",
        "fan.speed",
    ]
    cmd = [
        "nvidia-smi",
        "--query-gpu=" + ",".join(cols),
        "--format=csv,noheader,nounits",
    ]
    out = run_cmd(cmd)
    if not out:
        return {}
    line = out.splitlines()[0]
    # nvidia-smi returns comma separated
    parts = [p.strip() for p in line.split(",")]
    # map fields safely
    d = {}
    try:
        d["gpu_power_w"] = (
            float(parts[1]) if len(parts) > 1 and parts[1] != "" else math.nan
        )
        d["gpu_temp_c"] = (
            float(parts[2]) if len(parts) > 2 and parts[2] != "" else math.nan
        )
        d["gpu_util_pct"] = (
            float(parts[3]) if len(parts) > 3 and parts[3] != "" else math.nan
        )
        d["gpu_mem_util_pct"] = (
            float(parts[4]) if len(parts) > 4 and parts[4] != "" else math.nan
        )
        d["gpu_mem_used_mb"] = (
            float(parts[5]) if len(parts) > 5 and parts[5] != "" else math.nan
        )
        d["gpu_fan_pct"] = (
            float(parts[6]) if len(parts) > 6 and parts[6] != "" else math.nan
        )
    except Exception:
        pass
    return d


def read_rapl_w() -> float | None:
    # Read RAPL energy_uj and compute power as delta/dt if available in /sys
    rapl = "/sys/class/powercap/intel-rapl:0/energy_uj"
    if not os.path.exists(rapl):
        return None
    try:
        with open(rapl) as f:
            v = f.read().strip()
        return float(v)  # but in microJoules - caller must compute delta
    except Exception:
        return None


def read_hwmon_label(match: str) -> float | None:
    # read first matching labeled temp from hwmon
    try:
        for hw in sorted(os.listdir("/sys/class/hwmon")):
            hwpath = os.path.join("/sys/class/hwmon", hw)
            if not os.path.isdir(hwpath):
                continue
            for name in sorted(os.listdir(hwpath)):
                if name.endswith("_label"):
                    try:
                        lab = open(os.path.join(hwpath, name)).read().strip()
                    except Exception:
                        lab = ""
                    if match.lower() in lab.lower():
                        base = name[:-6]
                        valfile = os.path.join(hwpath, base + "_input")
                        try:
                            raw = open(valfile).read().strip()
                            # hwmon temps are commonly in millidegrees
                            return float(raw) / 1000.0
                        except Exception:
                            continue
        # fallback: look for any temp_input files
        for hw in sorted(os.listdir("/sys/class/hwmon")):
            hwpath = os.path.join("/sys/class/hwmon", hw)
            for name in sorted(os.listdir(hwpath)):
                if name.endswith("_input") and name.startswith("temp"):
                    try:
                        raw = open(os.path.join(hwpath, name)).read().strip()
                        return float(raw) / 1000.0
                    except Exception:
                        continue
    except Exception:
        pass
    return None


def metrics_loop(interval: float, port: int):
    # Prometheus metrics (Gauges)
    g_gpu_power = Gauge("jn_gpu_power_w", "GPU power draw in watts")
    g_gpu_temp = Gauge("jn_gpu_temp_c", "GPU temperature C")
    g_gpu_util = Gauge("jn_gpu_util_pct", "GPU utilization percent")
    g_gpu_mem_util = Gauge("jn_gpu_mem_util_pct", "GPU memory utilization percent")
    g_gpu_mem_used = Gauge("jn_gpu_mem_used_mb", "GPU memory used MB")
    g_gpu_fan = Gauge("jn_gpu_fan_pct", "GPU fan percent")

    g_cpu_pkg_w = Gauge("jn_cpu_pkg_w", "CPU package power (W) from RAPL estimate")
    g_cpu_pkg_temp = Gauge("jn_cpu_pkg_temp_c", "CPU package temp C")
    g_cpu_core_max = Gauge("jn_cpu_core_max_c", "Maximum core temp C")
    g_t_sensor = Gauge("jn_t_sensor_c", "Board T sensor temp C")
    g_chipset = Gauge("jn_chipset_temp_c", "Chipset temp C")
    g_vrm = Gauge("jn_vrm_temp_c", "VRM temp C")
    g_system_total = Gauge(
        "jn_system_total_w", "Estimated system total power GPU+CPU (W)"
    )

    # RAPL state for power computation
    prev_uJ = None
    prev_t = None

    while True:
        d = parse_nvidia_smi_one()
        if d:
            if "gpu_power_w" in d:
                g_gpu_power.set(d.get("gpu_power_w", float("nan")))
            if "gpu_temp_c" in d:
                g_gpu_temp.set(d.get("gpu_temp_c", float("nan")))
            if "gpu_util_pct" in d:
                g_gpu_util.set(d.get("gpu_util_pct", float("nan")))
            if "gpu_mem_util_pct" in d:
                g_gpu_mem_util.set(d.get("gpu_mem_util_pct", float("nan")))
            if "gpu_mem_used_mb" in d:
                g_gpu_mem_used.set(d.get("gpu_mem_used_mb", float("nan")))
            if "gpu_fan_pct" in d:
                g_gpu_fan.set(d.get("gpu_fan_pct", float("nan")))

        # RAPL
        now = time.time()
        uj = read_rapl_w()
        cpu_w = None
        if uj is not None:
            if prev_uJ is not None and prev_t is not None:
                # delta_uJ / delta_s -> uJ/s -> W
                try:
                    delta = float(uj) - float(prev_uJ)
                    dt = now - prev_t
                    if dt > 0:
                        cpu_w = (delta / dt) / 1e6
                except Exception:
                    cpu_w = None
            prev_uJ = uj
            prev_t = now

        if cpu_w is not None:
            g_cpu_pkg_w.set(cpu_w)

        # hwmon temps
        cpu_pkg_temp = read_hwmon_label("Package") or read_hwmon_label("CPU")
        cpu_core_max = read_hwmon_label("Core") or None
        t_sensor = read_hwmon_label("T_Sensor") or read_hwmon_label("T_Sensor")
        chipset = read_hwmon_label("Chipset") or read_hwmon_label("PCH")
        vrm = read_hwmon_label("VRM") or read_hwmon_label("vrm")

        if cpu_pkg_temp is not None:
            g_cpu_pkg_temp.set(cpu_pkg_temp)
        if cpu_core_max is not None:
            g_cpu_core_max.set(cpu_core_max)
        if t_sensor is not None:
            g_t_sensor.set(t_sensor)
        if chipset is not None:
            g_chipset.set(chipset)
        if vrm is not None:
            g_vrm.set(vrm)

        # system_total estimate
        try:
            gpu_p = d.get("gpu_power_w") if d else None
            s_total = None
            if cpu_w is not None and gpu_p is not None:
                s_total = float(cpu_w) + float(gpu_p)
                g_system_total.set(s_total)
        except Exception:
            pass

        time.sleep(interval)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=9118)
    p.add_argument("--interval", type=float, default=1.0)
    args = p.parse_args(argv)

    start_http_server(args.port)
    print(
        f"Prometheus exporter listening on :{args.port}, scraping interval={args.interval}s"
    )
    metrics_loop(args.interval, args.port)


if __name__ == "__main__":
    main()
