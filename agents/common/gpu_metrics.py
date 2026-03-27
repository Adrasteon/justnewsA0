"""
Minimal structured GPU event logger for JustNews.

Provides a tiny API to record per-request GPU events in structured JSONL format.

API:
 - start_event(**meta) -> event_id
 - end_event(event_id, **outcome)
 - emit_instant(**event)

This intentionally keeps dependencies minimal: it will try to use `torch` if available
and `nvidia-smi` as a fallback for utilization metrics.
"""

import json
import os
import subprocess
import time
import uuid
from datetime import UTC, datetime
from threading import Lock

OUT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "logs", "gpu_events.jsonl")
)
_events = {}
_lock = Lock()


def _ensure_out_dir():
    d = os.path.dirname(OUT_PATH)
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _read_nvidia_smi_util(gpu_index: int = 0):
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,utilization.memory,temperature.gpu,power.draw",
                "--format=csv,nounits,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if proc.returncode != 0:
            return None
        line = proc.stdout.strip().splitlines()[gpu_index]
        parts = [p.strip() for p in line.split(",")]
        return {
            "utilization_gpu_pct": float(parts[0]) if parts[0] else None,
            "utilization_mem_pct": float(parts[1]) if parts[1] else None,
            "temperature_c": float(parts[2]) if parts[2] else None,
            "power_draw_w": float(parts[3]) if parts[3] else None,
        }
    except Exception:
        return None


def _read_torch_memory():
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        out = []
        for i in range(torch.cuda.device_count()):
            out.append(
                {
                    "gpu_index": i,
                    "memory_allocated_mb": torch.cuda.memory_allocated(i) / 1024**2,
                    "memory_reserved_mb": torch.cuda.memory_reserved(i) / 1024**2,
                }
            )
        return out
    except Exception:
        return None


def _write_event(record: dict):
    _ensure_out_dir()
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def start_event(**meta) -> str:
    """Start an event and return an event_id. meta may include agent, operation, batch_size, etc."""
    event_id = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    with _lock:
        _events[event_id] = {"meta": meta, "start_time": now}
    return event_id


def end_event(event_id: str, **outcome):
    """Complete an event started with start_event and write a structured JSONL line.

    outcome may include processing_time_s, success, result, error, etc.
    """
    with _lock:
        ev = _events.pop(event_id, None)
    record = {}
    if ev is None:
        # emit a best-effort record
        record["meta"] = {}
        record["start_time"] = None
    else:
        record["meta"] = ev.get("meta", {})
        record["start_time"] = ev.get("start_time")

    record["end_time"] = datetime.now(UTC).isoformat()
    # merge outcome data
    record.update(outcome)

    # enrich with lightweight runtime samples
    try:
        mem = _read_torch_memory()
        if mem is not None:
            record["torch_memory"] = mem
        else:
            # try a single nvidia-smi row
            nvsmi = _read_nvidia_smi_util(0)
            if nvsmi is not None:
                record["nvidia_smi"] = nvsmi
    except Exception:
        pass

    # compute derived processing_time if not provided and we have start_time
    try:
        if "processing_time_s" not in record and record.get("start_time"):
            st = record.get("start_time")
            # parse ISO strings to epoch
            st_epoch = time.mktime(time.strptime(st.split(".")[0], "%Y-%m-%dT%H:%M:%S"))
            et = datetime.now(UTC).isoformat()
            et_epoch = time.mktime(time.strptime(et.split(".")[0], "%Y-%m-%dT%H:%M:%S"))
            record["processing_time_s"] = max(0.0, et_epoch - st_epoch)
    except Exception:
        # ignore parsing errors
        pass

    record["written_at"] = datetime.now(UTC).isoformat()
    _write_event(record)
    return record


def emit_instant(**event):
    """Write a single instant event (no start_event required)."""
    record = {
        "instant": True,
        "meta": event,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    try:
        mem = _read_torch_memory()
        if mem is not None:
            record["torch_memory"] = mem
        else:
            nvsmi = _read_nvidia_smi_util(0)
            if nvsmi is not None:
                record["nvidia_smi"] = nvsmi
    except Exception:
        pass
    _write_event(record)
    return record
