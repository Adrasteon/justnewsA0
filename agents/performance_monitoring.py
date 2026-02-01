"""Lightweight performance monitoring utilities for crawler agents."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    articles_processed: int = 0
    sites_crawled: int = 0
    errors: int = 0
    mode_usage: dict[str, int] = field(
        default_factory=lambda: {"ai_enhanced": 0, "generic": 0}
    )
    start_time: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        uptime = time.time() - self.start_time
        return {
            "articles_processed": self.articles_processed,
            "sites_crawled": self.sites_crawled,
            "errors": self.errors,
            "mode_usage": dict(self.mode_usage),
            "uptime_seconds": uptime,
        }


class PerformanceMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.metrics = PerformanceMetrics()

    def record_site_result(
        self, *, articles: int, mode: str, error: bool = False
    ) -> None:
        with self._lock:
            self.metrics.articles_processed += articles
            self.metrics.sites_crawled += 1
            if error:
                self.metrics.errors += 1
            if mode in self.metrics.mode_usage:
                self.metrics.mode_usage[mode] += 1

    def reset(self) -> None:
        with self._lock:
            self.metrics = PerformanceMetrics()

    def get_current_metrics(self) -> dict[str, Any]:
        with self._lock:
            return self.metrics.to_dict()


class PerformanceOptimizer:
    def __init__(self, monitor: PerformanceMonitor) -> None:
        self.monitor = monitor

    def recommend_strategy(self) -> str | None:
        metrics = self.monitor.get_current_metrics()
        usage = metrics["mode_usage"]
        if not usage:
            return None
        return max(usage, key=usage.get)


_MONITOR = PerformanceMonitor()
_MONITOR_THREAD: threading.Thread | None = None
_MONITOR_EVENT = threading.Event()


def get_performance_monitor() -> PerformanceMonitor:
    return _MONITOR


def reset_performance_metrics() -> None:
    _MONITOR.reset()


def _monitor_loop(interval: float) -> None:
    logger.info("Background performance monitor started (interval %.0fs)", interval)
    while not _MONITOR_EVENT.wait(interval):
        metrics = _MONITOR.get_current_metrics()
        logger.debug("Performance snapshot: %s", metrics)
    logger.info("Background performance monitor stopped")


def start_performance_monitoring(interval_seconds: float = 60.0) -> None:
    global _MONITOR_THREAD
    if _MONITOR_THREAD and _MONITOR_THREAD.is_alive():
        return
    _MONITOR_EVENT.clear()
    _MONITOR_THREAD = threading.Thread(
        target=_monitor_loop, args=(interval_seconds,), daemon=True
    )
    _MONITOR_THREAD.start()


def stop_performance_monitoring() -> None:
    if _MONITOR_THREAD and _MONITOR_THREAD.is_alive():
        _MONITOR_EVENT.set()


def export_performance_metrics() -> dict[str, Any]:
    return _MONITOR.get_current_metrics()


__all__ = [
    "PerformanceMetrics",
    "PerformanceMonitor",
    "PerformanceOptimizer",
    "export_performance_metrics",
    "get_performance_monitor",
    "reset_performance_metrics",
    "start_performance_monitoring",
    "stop_performance_monitoring",
]
