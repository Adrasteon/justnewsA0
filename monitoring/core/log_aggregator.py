"""
JustNews Log Aggregator

Centralized log collection, processing, and distribution system for the
JustNews observability platform.
"""

import asyncio
import json
import logging
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import aiofiles
import aiohttp

from .log_collector import LogEntry


class AggregationStrategy(Enum):
    """Log aggregation strategies"""

    TIME_WINDOW = "time_window"
    SIZE_BASED = "size_based"
    EVENT_COUNT = "event_count"


class StorageBackend(Enum):
    """Supported storage backends"""

    FILE = "file"
    ELASTICSEARCH = "elasticsearch"
    OPENSEARCH = "opensearch"
    CLOUDWATCH = "cloudwatch"
    SPLUNK = "splunk"


@dataclass
class AggregationConfig:
    """Log aggregation configuration"""

    strategy: AggregationStrategy = AggregationStrategy.TIME_WINDOW
    time_window_seconds: int = 60
    max_batch_size: int = 1000
    max_buffer_size: int = 10000
    flush_interval_seconds: float = 30.0
    compression_enabled: bool = True
    retention_days: int = 30


@dataclass
class StorageConfig:
    """Storage backend configuration"""

    backend: StorageBackend = StorageBackend.FILE
    file_path: str = "logs/aggregated"
    elasticsearch_url: str | None = None
    elasticsearch_index: str = "justnews-logs"
    cloudwatch_log_group: str | None = None
    splunk_url: str | None = None
    splunk_token: str | None = None


class LogAggregator:
    """
    Centralized log aggregator for JustNews.

    Collects logs from multiple agents, aggregates them according to configured
    strategies, and stores them in various backends for analysis and retention.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or self._get_default_config()

        # Parse aggregation config
        agg_data = self.config.get("aggregation", {}).copy()
        if isinstance(agg_data.get("strategy"), str):
            agg_data["strategy"] = AggregationStrategy(agg_data["strategy"])
        self.aggregation_config = AggregationConfig(**agg_data)

        # Parse storage config
        store_data = self.config.get("storage", {}).copy()
        if isinstance(store_data.get("backend"), str):
            store_data["backend"] = StorageBackend(store_data["backend"])
        self.storage_config = StorageConfig(**store_data)

        # Aggregation state
        self._log_buffer: list[LogEntry] = []
        self._last_flush_time = datetime.now(UTC)
        self._flush_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()

        # Storage backends
        self._storage_backends: list[Callable] = []
        self._setup_storage_backends()

        # Metrics
        self._logs_processed = 0
        self._batches_flushed = 0
        self._errors_count = 0

        # Cleanup task is scheduled lazily once an event loop is running
        self._cleanup_task: asyncio.Task | None = None

    def _ensure_cleanup_task(self) -> None:
        """Start the retention cleanup loop once an event loop is available."""
        if self._cleanup_task is not None:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called outside of a running loop (e.g., during sync test setup).
            # The cleanup loop is best-effort, so skip scheduling for now.
            return

        self._cleanup_task = loop.create_task(self._cleanup_old_logs())

    def _get_default_config(self) -> dict[str, Any]:
        """Get default aggregator configuration"""
        return {
            "aggregation": {
                "strategy": "time_window",
                "time_window_seconds": 60,
                "max_batch_size": 1000,
                "max_buffer_size": 10000,
                "flush_interval_seconds": 30.0,
                "compression_enabled": True,
                "retention_days": 30,
            },
            "storage": {"backend": "file", "file_path": "logs/aggregated"},
        }

    def _setup_storage_backends(self) -> None:
        """Setup storage backends based on configuration"""
        if self.storage_config.backend == StorageBackend.FILE:
            self._storage_backends.append(self._store_to_file)
        elif self.storage_config.backend == StorageBackend.ELASTICSEARCH:
            self._storage_backends.append(self._store_to_elasticsearch)
        elif self.storage_config.backend == StorageBackend.OPENSEARCH:
            self._storage_backends.append(self._store_to_opensearch)
        elif self.storage_config.backend == StorageBackend.CLOUDWATCH:
            self._storage_backends.append(self._store_to_cloudwatch)
        elif self.storage_config.backend == StorageBackend.SPLUNK:
            self._storage_backends.append(self._store_to_splunk)

    async def start(self) -> None:
        """Start the log aggregator"""
        self._ensure_cleanup_task()
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def shutdown(self) -> None:
        """Shutdown the log aggregator"""
        self._shutdown_event.set()

        if self._flush_task:
            await self._flush_task

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Final flush
        await self._flush_buffer()

    async def aggregate_log(self, log_entry: LogEntry) -> None:
        """Aggregate a log entry"""
        self._ensure_cleanup_task()
        try:
            self._log_buffer.append(log_entry)
            self._logs_processed += 1

            # Check if we should flush based on strategy
            should_flush = False

            if self.aggregation_config.strategy == AggregationStrategy.SIZE_BASED:
                should_flush = (
                    len(self._log_buffer) >= self.aggregation_config.max_batch_size
                )
            elif self.aggregation_config.strategy == AggregationStrategy.EVENT_COUNT:
                should_flush = (
                    len(self._log_buffer) >= self.aggregation_config.max_batch_size
                )
            elif self.aggregation_config.strategy == AggregationStrategy.TIME_WINDOW:
                time_since_last_flush = (
                    datetime.now(UTC) - self._last_flush_time
                ).total_seconds()
                should_flush = (
                    time_since_last_flush >= self.aggregation_config.time_window_seconds
                )

            # Emergency flush if buffer is too large
            if len(self._log_buffer) >= self.aggregation_config.max_buffer_size:
                should_flush = True

            if should_flush:
                await self._flush_buffer()

        except Exception as e:
            self._errors_count += 1
            logging.error(f"Error aggregating log: {e}")

    async def _flush_buffer(self) -> None:
        """Flush the current log buffer to storage"""
        if not self._log_buffer:
            return

        try:
            # Create batch data
            batch_data = [entry.to_dict() for entry in self._log_buffer]

            # Store to all configured backends
            for backend in self._storage_backends:
                try:
                    await backend(batch_data)
                except Exception as e:
                    logging.error(f"Storage backend error: {e}")
                    self._errors_count += 1

            self._batches_flushed += 1
            self._last_flush_time = datetime.now(UTC)
            self._log_buffer.clear()

        except Exception as e:
            self._errors_count += 1
            logging.error(f"Error flushing log buffer: {e}")

    async def _periodic_flush(self) -> None:
        """Periodic flush task"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(self.aggregation_config.flush_interval_seconds)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Periodic flush error: {e}")

    async def _store_to_file(self, batch_data: list[dict[str, Any]]) -> None:
        """Store logs to file system"""
        try:
            # Create timestamped filename
            timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            batch_id = secrets.token_hex(4)
            filename = (
                f"{self.storage_config.file_path}/logs_{timestamp}_{batch_id}.json"
            )

            # Ensure directory exists
            os.makedirs(os.path.dirname(filename), exist_ok=True)

            # Write batch data
            async with aiofiles.open(filename, "w") as f:
                if self.aggregation_config.compression_enabled:
                    # Simple compression - could be enhanced with gzip
                    data = json.dumps(batch_data, indent=2)
                else:
                    data = json.dumps(batch_data, indent=2)
                await f.write(data)

        except Exception as e:
            logging.error(f"File storage error: {e}")
            raise

    async def _store_to_elasticsearch(self, batch_data: list[dict[str, Any]]) -> None:
        """Store logs to Elasticsearch"""
        if not self.storage_config.elasticsearch_url:
            return

        try:
            url = f"{self.storage_config.elasticsearch_url}/{self.storage_config.elasticsearch_index}/_bulk"

            # Prepare bulk request
            bulk_data = ""
            for entry in batch_data:
                # Create bulk index command
                index_cmd = json.dumps(
                    {
                        "index": {
                            "_index": self.storage_config.elasticsearch_index,
                            "_id": entry.get("correlation_id", secrets.token_hex(8)),
                        }
                    }
                )
                bulk_data += index_cmd + "\n"
                bulk_data += json.dumps(entry) + "\n"

            # Send to Elasticsearch
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=bulk_data,
                    headers={"Content-Type": "application/x-ndjson"},
                ) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        raise Exception(
                            f"Elasticsearch error {response.status}: {error_text}"
                        )

        except Exception as e:
            logging.error(f"Elasticsearch storage error: {e}")
            raise

    async def _store_to_opensearch(self, batch_data: list[dict[str, Any]]) -> None:
        """Store logs to OpenSearch (similar to Elasticsearch)"""
        # OpenSearch uses the same API as Elasticsearch
        await self._store_to_elasticsearch(batch_data)

    async def _store_to_cloudwatch(self, batch_data: list[dict[str, Any]]) -> None:
        """Store logs to AWS CloudWatch"""
        if not self.storage_config.cloudwatch_log_group:
            return

        try:
            # This would require boto3 and AWS credentials
            # Implementation would create log streams and put log events
            # For now, just log that this would be implemented
            logging.info(
                f"Would store {len(batch_data)} logs to CloudWatch group {self.storage_config.cloudwatch_log_group}"
            )

        except Exception as e:
            logging.error(f"CloudWatch storage error: {e}")
            raise

    async def _store_to_splunk(self, batch_data: list[dict[str, Any]]) -> None:
        """Store logs to Splunk"""
        if not self.storage_config.splunk_url or not self.storage_config.splunk_token:
            return

        try:
            url = f"{self.storage_config.splunk_url}/services/collector/event"

            # Send each log entry as separate event
            async with aiohttp.ClientSession() as session:
                for entry in batch_data:
                    event_data = {
                        "event": entry,
                        "sourcetype": "justnews:log",
                        "index": "justnews_logs",
                    }

                    async with session.post(
                        url,
                        json=event_data,
                        headers={
                            "Authorization": f"Splunk {self.storage_config.splunk_token}",
                            "Content-Type": "application/json",
                        },
                    ) as response:
                        if response.status not in [200, 201]:
                            error_text = await response.text()
                            raise Exception(
                                f"Splunk error {response.status}: {error_text}"
                            )

        except Exception as e:
            logging.error(f"Splunk storage error: {e}")
            raise

    async def _cleanup_old_logs(self) -> None:
        """Cleanup old log files based on retention policy"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(86400)  # Run daily

                cutoff_date = datetime.now(UTC) - timedelta(
                    days=self.aggregation_config.retention_days
                )
                cutoff_timestamp = cutoff_date.strftime("%Y%m%d")

                # Clean up file-based logs
                if self.storage_config.backend == StorageBackend.FILE:
                    log_dir = Path(self.storage_config.file_path)
                    if log_dir.exists():
                        for log_file in log_dir.glob("logs_*.json"):
                            file_date = log_file.stem.split("_")[
                                1
                            ]  # Extract date from filename
                            if file_date < cutoff_timestamp:
                                try:
                                    log_file.unlink()
                                    logging.info(f"Cleaned up old log file: {log_file}")
                                except Exception as e:
                                    logging.error(f"Error cleaning up {log_file}: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Log cleanup error: {e}")

    async def get_status(self) -> dict[str, Any]:
        """Get aggregator status"""
        return {
            "logs_processed": self._logs_processed,
            "batches_flushed": self._batches_flushed,
            "buffer_size": len(self._log_buffer),
            "errors_count": self._errors_count,
            "last_flush_time": self._last_flush_time.isoformat(),
            "storage_backend": self.storage_config.backend.value,
            "aggregation_strategy": self.aggregation_config.strategy.value,
        }

    def add_storage_backend(self, backend: Callable) -> None:
        """Add custom storage backend"""
        self._storage_backends.append(backend)

    def remove_storage_backend(self, backend: Callable) -> None:
        """Remove storage backend"""
        if backend in self._storage_backends:
            self._storage_backends.remove(backend)


# Global aggregator instance
_global_aggregator: LogAggregator | None = None


def get_log_aggregator(config: dict[str, Any] | None = None) -> LogAggregator:
    """Get or create global log aggregator"""
    global _global_aggregator

    if _global_aggregator is None:
        _global_aggregator = LogAggregator(config)

    return _global_aggregator


def init_log_aggregation(config: dict[str, Any] | None = None) -> LogAggregator:
    """Initialize log aggregation system"""
    aggregator = LogAggregator(config)
    global _global_aggregator
    _global_aggregator = aggregator
    return aggregator
