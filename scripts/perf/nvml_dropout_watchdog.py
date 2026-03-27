#!/usr/bin/env python3
"""NVML dropout watchdog.

This utility uses the nvidia-ml-py (pynvml) bindings to continuously sample GPU
state and capture NVML exceptions. It keeps a rolling buffer of the last N
samples and will dump that context whenever NVML stops responding so we can
pinpoint why the library dropped out under load.

Typical usage during a load test:

    python3 scripts/perf/nvml_dropout_watchdog.py \
        --log-file /var/log/justnews-perf/nvml_watchdog.jsonl \
        --interval 1.0 \
        --context-samples 120 &
    WATCHDOG_PID=$!

    # run the medium load test (for example the GPU activity agent or
    # simulate_concurrent_inference.py)

    wait ${WATCHDOG_PID}

Log entries are newline-delimited JSON and can be filtered with jq, e.g.:

    jq 'select(.event == "nvml_exception")' /var/log/justnews-perf/nvml_watchdog.jsonl
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import pathlib
import signal
import subprocess
import sys
import threading
import time
from typing import Any

try:
    import pynvml
except ModuleNotFoundError as exc:  # pragma: no cover - simple import guard
    raise SystemExit(
        "pynvml (nvidia-ml-py) is required. Install via pip install nvidia-ml-py"
    ) from exc


_EVENT_FLAGS: list[tuple[str, int]] = []
for _name in [
    ("single_bit_ecc_error", "NVML_EVENT_TYPE_SINGLE_BIT_ECC_ERROR"),
    ("double_bit_ecc_error", "NVML_EVENT_TYPE_DOUBLE_BIT_ECC_ERROR"),
    ("pstate_change", "NVML_EVENT_TYPE_PSTATE_CHANGE"),
    ("clock_change", "NVML_EVENT_TYPE_CLOCK_CHANGE"),
    ("xid_critical_error", "NVML_EVENT_TYPE_XID_CRITICAL_ERROR"),
    ("power_source_change", "NVML_EVENT_TYPE_POWER_SOURCE_CHANGE"),
    ("temperature_threshold", "NVML_EVENT_TYPE_TEMPERATURE_THRESHOLD"),
    ("performance_state_change", "NVML_EVENT_TYPE_PERFORMANCE_STATE_CHANGE"),
    ("clock_throttle", "NVML_EVENT_TYPE_CLOCK_THROTTLE"),
]:
    flag = getattr(pynvml, _name[1], 0)
    if flag:
        _EVENT_FLAGS.append((_name[0], flag))


class NvmlDropoutWatchdog:
    """Background sampler that records NVML state and exceptions."""

    def __init__(
        self,
        interval: float,
        context_samples: int,
        log_file: pathlib.Path,
        emit_samples: bool,
        capture_dmesg: bool,
        dmesg_lines: int,
    ) -> None:
        self.interval = max(interval, 0.1)
        self.context = collections.deque(maxlen=context_samples)
        self.log_file = log_file
        self.emit_samples = emit_samples
        self.capture_dmesg = capture_dmesg
        self.dmesg_lines = dmesg_lines
        self._stop = threading.Event()
        self._event_thread: threading.Thread | None = None
        self._event_set = None
        self._fh = None
        self._device_count = 0

    @staticmethod
    def _now_iso() -> str:
        return _dt.datetime.now(_dt.UTC).isoformat(timespec="milliseconds") + "Z"

    def _write_log(self, payload: dict[str, Any]) -> None:
        if self._fh is None:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.log_file.open("a", encoding="utf-8")
        payload.setdefault("ts", self._now_iso())
        payload.setdefault("component", "nvml_watchdog")
        self._fh.write(json.dumps(payload, sort_keys=True) + "\n")
        self._fh.flush()
        print(json.dumps(payload, sort_keys=True))

    def start(self) -> None:
        self._write_log({"event": "watchdog_start", "log_path": str(self.log_file)})
        self._init_nvml()
        self._start_event_thread()
        try:
            while not self._stop.is_set():
                self._sample_once()
                time.sleep(self.interval)
        except KeyboardInterrupt:
            self._write_log({"event": "watchdog_stop", "reason": "keyboard_interrupt"})
        finally:
            self.shutdown()

    def stop(self) -> None:
        self._stop.set()

    def shutdown(self) -> None:
        if self._event_thread and self._event_thread.is_alive():
            self._stop.set()
            self._event_thread.join(timeout=1.0)
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        if self._fh:
            self._fh.close()
            self._fh = None

    def _init_nvml(self) -> None:
        try:
            pynvml.nvmlInit()
            self._device_count = pynvml.nvmlDeviceGetCount()
            driver = pynvml.nvmlSystemGetDriverVersion()
            nvml_version = pynvml.nvmlSystemGetNVMLVersion()
            self._write_log(
                {
                    "event": "nvml_initialized",
                    "driver_version": driver.decode()
                    if isinstance(driver, bytes)
                    else driver,
                    "nvml_version": nvml_version.decode()
                    if isinstance(nvml_version, bytes)
                    else nvml_version,
                    "device_count": self._device_count,
                }
            )
        except pynvml.NVMLError as exc:
            self._write_log({"event": "nvml_init_error", "error": str(exc)})
            raise

    def _restart_nvml(self) -> None:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        time.sleep(0.5)
        try:
            self._init_nvml()
        except pynvml.NVMLError as exc:  # pragma: no cover - catastrophic failure path
            self._write_log({"event": "nvml_restart_failed", "error": str(exc)})
            raise

    def _sample_once(self) -> None:
        sample = {
            "event": "nvml_sample",
            "gpus": [],
        }
        try:
            for idx in range(self._device_count):
                gpu_sample = self._collect_gpu(idx)
                sample["gpus"].append(gpu_sample)
        except pynvml.NVMLError as exc:
            self._record_dropout("sample", exc)
            self._restart_nvml()
            return

        self.context.append(sample)
        if self.emit_samples:
            self._write_log(sample)

    def _collect_gpu(self, idx: int) -> dict[str, Any]:
        handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
        name = pynvml.nvmlDeviceGetName(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        pstate = pynvml.nvmlDeviceGetPerformanceState(handle)
        clocks_sm = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_SM)
        clocks_mem = pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)
        power_w = None
        try:
            power_w = round(pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0, 2)
        except pynvml.NVMLError:
            power_w = None
        running_procs = []
        try:
            procs = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
            for proc in procs:
                running_procs.append(
                    {
                        "pid": getattr(proc, "pid", None),
                        "used_gpu_memory_mb": round(
                            getattr(proc, "usedGpuMemory", 0) / 1024**2, 2
                        ),
                    }
                )
        except pynvml.NVMLError:
            pass

        return {
            "index": idx,
            "name": name.decode() if isinstance(name, bytes) else name,
            "temperature_c": temp,
            "utilization_gpu_pct": getattr(util, "gpu", None),
            "utilization_mem_pct": getattr(util, "memory", None),
            "memory_total_mb": round(mem.total / 1024**2, 2),
            "memory_used_mb": round(mem.used / 1024**2, 2),
            "pstate": pstate,
            "sm_clock_mhz": clocks_sm,
            "mem_clock_mhz": clocks_mem,
            "power_w": power_w,
            "running_procs": running_procs,
        }

    def _record_dropout(self, stage: str, exc: Exception) -> None:
        context_snapshot = list(self.context)
        payload: dict[str, Any] = {
            "event": "nvml_exception",
            "stage": stage,
            "error": str(exc),
            "context_samples": context_snapshot,
        }
        if self.capture_dmesg:
            payload["dmesg_tail"] = self._capture_dmesg()
        self._write_log(payload)

    def _capture_dmesg(self) -> str | None:
        try:
            proc = subprocess.run(
                ["dmesg", "--color=never"],
                check=False,
                capture_output=True,
                text=True,
            )
            lines = proc.stdout.strip().splitlines()
            if not lines:
                return None
            return "\n".join(lines[-self.dmesg_lines :])
        except Exception:
            return None

    def _start_event_thread(self) -> None:
        if not _EVENT_FLAGS:
            return
        try:
            event_set = pynvml.nvmlEventSetCreate()
            for idx in range(self._device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
                mask = 0
                for _, flag in _EVENT_FLAGS:
                    mask |= flag
                pynvml.nvmlDeviceRegisterEvents(handle, mask, event_set)
            self._event_set = event_set
        except pynvml.NVMLError as exc:
            self._write_log(
                {
                    "event": "nvml_event_registration_failed",
                    "error": str(exc),
                }
            )
            return

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    event = pynvml.nvmlEventSetWait(
                        event_set, int(self.interval * 1000)
                    )
                    if event:
                        names = [
                            name
                            for name, flag in _EVENT_FLAGS
                            if event.eventType & flag
                        ]
                        self._write_log(
                            {
                                "event": "nvml_event",
                                "gpu_index": event.device,
                                "raw_type": event.eventType,
                                "decoded_types": names,
                                "event_data": event.eventData,
                            }
                        )
                except pynvml.NVMLError as exc:
                    if exc.value == pynvml.NVML_ERROR_TIMEOUT:
                        continue
                    self._record_dropout("event_loop", exc)
                    break

        self._event_thread = threading.Thread(target=_loop, daemon=True)
        self._event_thread.start()


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NVML dropout watchdog")
    p.add_argument(
        "--interval", type=float, default=1.0, help="Sampling interval seconds"
    )
    p.add_argument(
        "--context-samples",
        type=int,
        default=120,
        help="How many recent samples to keep for context",
    )
    p.add_argument(
        "--log-file",
        type=pathlib.Path,
        default=pathlib.Path("/var/log/justnews-perf/nvml_watchdog.jsonl"),
    )
    p.add_argument(
        "--emit-samples",
        action="store_true",
        help="Write every sample to the log (default only logs on events)",
    )
    p.add_argument(
        "--capture-dmesg",
        action="store_true",
        help="Include dmesg tail when NVML errors occur",
    )
    p.add_argument(
        "--dmesg-lines",
        type=int,
        default=50,
        help="How many dmesg lines to capture when enabled",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    watchdog = NvmlDropoutWatchdog(
        interval=args.interval,
        context_samples=args.context_samples,
        log_file=args.log_file,
        emit_samples=args.emit_samples,
        capture_dmesg=args.capture_dmesg,
        dmesg_lines=args.dmesg_lines,
    )

    def _handle_signal(signum, _frame):  # pragma: no cover - signal path
        watchdog._write_log({"event": "watchdog_stop", "reason": f"signal_{signum}"})
        watchdog.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _handle_signal)

    watchdog.start()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
