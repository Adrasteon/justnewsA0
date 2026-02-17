"""Lightweight persistence layer for the dashboard service.

This module provides a file-backed storage implementation used by the
FastAPI dashboard agent. It keeps the interface expected by
``dashboard_engine`` while remaining safe to import even when the real
backends are unavailable. Data is stored in JSON Lines files beneath a
configurable root directory so that the service can operate without a
full database dependency during development or degraded operation.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)

_STORAGE_INSTANCE: DashboardStorage | None = None


class DashboardStorage:
    """File-backed storage for dashboard metrics and alerts."""

    def __init__(self, base_path: Path | None = None, max_records: int = 10000) -> None:
        storage_root = os.getenv("JUSTNEWS_DASHBOARD_STORAGE")
        if base_path is None:
            if storage_root:
                base_path = Path(storage_root)
            else:
                base_path = Path(__file__).resolve().parents[2] / "logs" / "dashboard"

        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.metrics_path = self.base_path / "gpu_metrics.jsonl"
        self.allocations_path = self.base_path / "allocations.jsonl"
        self.alerts_path = self.base_path / "alerts.jsonl"

        self.max_records = max_records
        self._lock = threading.Lock()

    # Public API -----------------------------------------------------
    def store_gpu_metrics(self, payload: dict[str, Any]) -> None:
        record = self._normalise_metric_payload(payload)
        self._append_jsonl(self.metrics_path, record)

    def get_gpu_metrics_history(
        self,
        hours: int,
        gpu_index: int | None = None,
        metric_type: str | None = None,
    ) -> list[dict[str, Any]]:
        cutoff = time.time() - max(hours, 0) * 3600
        records = self._read_jsonl(self.metrics_path)
        history: list[dict[str, Any]] = []

        for entry in records:
            ts = float(entry.get("timestamp", 0))
            if ts < cutoff:
                continue
            for gpu in entry.get("gpus", []):
                if gpu_index is not None and gpu.get("index") != gpu_index:
                    continue
                value = dict(gpu)
                value["timestamp"] = ts
                if metric_type:
                    value["value"] = self._select_metric_value(value, metric_type)
                history.append(value)

        return history

    def get_agent_allocation_history(
        self,
        hours: int,
        agent_name: str | None = None,
    ) -> list[dict[str, Any]]:
        cutoff = time.time() - max(hours, 0) * 3600
        records = self._read_jsonl(self.allocations_path)
        history: list[dict[str, Any]] = []

        for entry in records:
            ts = float(entry.get("timestamp", 0))
            if ts < cutoff:
                continue
            if agent_name and entry.get("agent_name") != agent_name:
                continue
            history.append(entry)

        return history

    def get_performance_trends(self, hours: int) -> list[dict[str, Any]]:
        # Aggregate basic utilisation statistics from stored GPU metrics.
        cutoff = time.time() - max(hours, 0) * 3600
        records = self._read_jsonl(self.metrics_path)
        buckets: dict[int, dict[str, Any]] = {}

        for entry in records:
            ts = float(entry.get("timestamp", 0))
            if ts < cutoff:
                continue
            bucket = int(ts // 300)  # five-minute buckets
            bucket_data = buckets.setdefault(
                bucket,
                {
                    "timestamp": bucket * 300,
                    "gpu_utilization_percent": [],
                    "memory_used_mb": [],
                },
            )
            for gpu in entry.get("gpus", []):
                util = self._to_float(gpu.get("gpu_utilization_percent"))
                mem = self._to_float(gpu.get("memory_used_mb"))
                if util is not None:
                    bucket_data["gpu_utilization_percent"].append(util)
                if mem is not None:
                    bucket_data["memory_used_mb"].append(mem)

        trends: list[dict[str, Any]] = []
        for bucket in sorted(buckets):
            data = buckets[bucket]
            trends.append(
                {
                    "timestamp": data["timestamp"],
                    "gpu_utilization_percent": self._mean(
                        data["gpu_utilization_percent"]
                    ),
                    "memory_used_mb": self._mean(data["memory_used_mb"]),
                }
            )
        return trends

    def get_recent_alerts(self, limit: int) -> list[dict[str, Any]]:
        records = self._read_jsonl(self.alerts_path)
        if not records:
            return []
        return records[-max(limit, 0) :]

    def get_storage_stats(self) -> dict[str, Any]:
        return {
            "base_path": str(self.base_path),
            "files": {
                "gpu_metrics": self._file_stats(self.metrics_path),
                "allocations": self._file_stats(self.allocations_path),
                "alerts": self._file_stats(self.alerts_path),
            },
            "timestamp": time.time(),
        }

    # Helper methods -------------------------------------------------
    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        if not record:
            return
        serialised = json.dumps(record, ensure_ascii=True, default=str)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(serialised + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.debug("Skipping malformed JSONL record in %s", path)
                    if len(records) > self.max_records:
                        records = records[-self.max_records :]
        except OSError as exc:
            logger.warning("Failed to read storage file %s: %s", path, exc)
        return records

    def _file_stats(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"exists": False, "size_bytes": 0, "records": 0}
        record_count = sum(1 for _ in self._iter_file_lines(path))
        return {
            "exists": True,
            "size_bytes": path.stat().st_size,
            "records": record_count,
        }

    def _iter_file_lines(self, path: Path) -> Iterable[str]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                yield from handle
        except OSError as exc:
            logger.warning("Failed to iterate storage file %s: %s", path, exc)

    def _normalise_metric_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = dict(payload)
        record.setdefault("timestamp", time.time())
        # Ensure GPU list contains serialisable primitives only.
        clean_gpus: list[dict[str, Any]] = []
        for gpu in record.get("gpus", []):
            clean_gpu = {key: self._serialisable(value) for key, value in gpu.items()}
            clean_gpus.append(clean_gpu)
        record["gpus"] = clean_gpus
        return record

    def _serialisable(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (list, tuple)):
            return [self._serialisable(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._serialisable(val) for key, val in value.items()}
        return str(value)

    def _select_metric_value(
        self, gpu: dict[str, Any], metric_type: str
    ) -> float | None:
        key_map = {
            "utilization": "gpu_utilization_percent",
            "memory": "memory_used_mb",
            "temperature": "temperature_celsius",
        }
        key = key_map.get(metric_type, metric_type)
        return self._to_float(gpu.get(key))

    def _to_float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _mean(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)


def get_storage() -> DashboardStorage:
    global _STORAGE_INSTANCE
    if _STORAGE_INSTANCE is None:
        _STORAGE_INSTANCE = DashboardStorage()
        logger.info("Dashboard storage initialized at %s", _STORAGE_INSTANCE.base_path)
    return _STORAGE_INSTANCE
