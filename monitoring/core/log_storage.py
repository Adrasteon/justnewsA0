"""
JustNews Log Storage

Searchable log storage and querying system for JustNews
observability platform.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

import aiofiles

from .log_collector import LogEntry, LogLevel


class QueryOperator(Enum):
    """Query operators for log searching"""

    EQUALS = "eq"
    NOT_EQUALS = "ne"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_EQUAL = "gte"
    LESS_EQUAL = "lte"
    REGEX = "regex"
    IN = "in"
    NOT_IN = "not_in"


@dataclass
class LogQuery:
    """Log search query"""

    filters: dict[str, Any] = None
    operators: dict[str, QueryOperator] = None
    time_range: tuple[datetime, datetime] | None = None
    limit: int = 100
    offset: int = 0
    sort_by: str = "timestamp"
    sort_order: str = "desc"  # "asc" or "desc"


@dataclass
class QueryResult:
    """Query result with pagination"""

    entries: list[LogEntry]
    total_count: int
    has_more: bool
    query_time_ms: float


class LogStorage:
    """
    Searchable log storage for JustNews.

    Provides efficient storage, indexing, and querying capabilities for log data
    with support for multiple storage backends and query optimization.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or self._get_default_config()

        # Storage configuration
        self.storage_path = Path(self.config["storage_path"])
        self.index_enabled = self.config["index_enabled"]
        self.compression_enabled = self.config["compression_enabled"]

        # Indexing
        self._index: dict[
            str, dict[str, list[str]]
        ] = {}  # field -> value -> file_paths
        self._reverse_index: dict[str, dict[str, Any]] = {}  # file_path -> metadata

        # Cache
        self._query_cache: dict[str, QueryResult] = {}
        self._cache_ttl_seconds = self.config["cache_ttl_seconds"]

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Load existing index
        if self.index_enabled:
            asyncio.create_task(self._load_index())

    def _get_default_config(self) -> dict[str, Any]:
        """Get default storage configuration"""
        return {
            "storage_path": "logs/storage",
            "index_enabled": True,
            "compression_enabled": True,
            "cache_ttl_seconds": 300,
            "max_query_time_seconds": 30,
            "index_fields": [
                "level",
                "agent_name",
                "logger_name",
                "error_type",
                "endpoint",
            ],
            "retention_days": 90,
        }

    async def store_logs(self, log_entries: list[LogEntry]) -> None:
        """Store log entries"""
        try:
            if not log_entries:
                return

            # Group entries by time window for efficient storage
            time_window = log_entries[0].timestamp.strftime("%Y%m%d_%H")
            filename = f"logs_{time_window}.json"
            filepath = self.storage_path / filename

            # Load existing entries if file exists
            existing_entries = []
            if filepath.exists():
                existing_entries = await self._load_log_file(filepath)

            # Add new entries
            existing_entries.extend(log_entries)

            # Sort by timestamp
            existing_entries.sort(key=lambda x: x.timestamp)

            # Save back to file
            await self._save_log_file(filepath, existing_entries)

            # Update index
            if self.index_enabled:
                await self._update_index(filename, log_entries)

        except Exception as e:
            logging.error(f"Error storing logs: {e}")
            raise

    async def query_logs(self, query: LogQuery) -> QueryResult:
        """Query logs with filtering and pagination"""
        start_time = datetime.now(UTC)

        try:
            # Check cache first
            cache_key = self._get_cache_key(query)
            if cache_key in self._query_cache:
                cached_result = self._query_cache[cache_key]
                # Check if cache is still valid
                if (
                    datetime.now(UTC) - start_time
                ).total_seconds() < self._cache_ttl_seconds:
                    return cached_result

            # Find relevant files
            relevant_files = await self._find_relevant_files(query)

            # Query each file
            all_entries = []
            for filepath in relevant_files:
                entries = await self._query_file(filepath, query)
                all_entries.extend(entries)

            # Apply global filters and sorting
            filtered_entries = await self._apply_filters(all_entries, query)

            # Sort results
            filtered_entries = self._sort_entries(filtered_entries, query)

            # Apply pagination
            total_count = len(filtered_entries)
            start_idx = query.offset
            end_idx = start_idx + query.limit
            paginated_entries = filtered_entries[start_idx:end_idx]

            # Create result
            result = QueryResult(
                entries=paginated_entries,
                total_count=total_count,
                has_more=end_idx < total_count,
                query_time_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000,
            )

            # Cache result
            self._query_cache[cache_key] = result

            return result

        except Exception as e:
            logging.error(f"Error querying logs: {e}")
            return QueryResult(
                entries=[],
                total_count=0,
                has_more=False,
                query_time_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000,
            )

    async def _find_relevant_files(self, query: LogQuery) -> list[Path]:
        """Find files that may contain relevant logs"""
        if not self.index_enabled:
            # Return all log files if no index
            return list(self.storage_path.glob("logs_*.json"))

        # Use index to find relevant files
        relevant_files = set()

        # Time range filtering
        if query.time_range:
            start_time, end_time = query.time_range
            start_window = start_time.strftime("%Y%m%d_%H")
            end_window = end_time.strftime("%Y%m%d_%H")

            # Find all time windows in range
            time_windows = []
            current = start_window
            while current <= end_window:
                time_windows.append(current)
                # Increment by hour
                dt = datetime.strptime(current, "%Y%m%d_%H")
                dt = dt + timedelta(hours=1)
                current = dt.strftime("%Y%m%d_%H")

            for window in time_windows:
                pattern = f"logs_{window}.json"
                filepath = self.storage_path / pattern
                if filepath.exists():
                    relevant_files.add(filepath)

        # Field-based filtering using index
        for field, value in (query.filters or {}).items():
            if field in self._index and value in self._index[field]:
                relevant_files.update(Path(fp) for fp in self._index[field][value])

        return (
            list(relevant_files)
            if relevant_files
            else list(self.storage_path.glob("logs_*.json"))
        )

    async def _query_file(self, filepath: Path, query: LogQuery) -> list[LogEntry]:
        """Query a specific log file"""
        try:
            entries = await self._load_log_file(filepath)

            # Apply time range filter
            if query.time_range:
                start_time, end_time = query.time_range
                entries = [
                    entry
                    for entry in entries
                    if start_time <= entry.timestamp <= end_time
                ]

            # Apply field filters
            if query.filters:
                filtered_entries = []
                for entry in entries:
                    match = True
                    for field, value in query.filters.items():
                        operator = (
                            query.operators.get(field, QueryOperator.EQUALS)
                            if query.operators
                            else QueryOperator.EQUALS
                        )

                        entry_value = getattr(entry, field, None)
                        if not self._matches_operator(entry_value, value, operator):
                            match = False
                            break

                    if match:
                        filtered_entries.append(entry)

                entries = filtered_entries

            return entries

        except Exception as e:
            logging.error(f"Error querying file {filepath}: {e}")
            return []

    async def _apply_filters(
        self, entries: list[LogEntry], query: LogQuery
    ) -> list[LogEntry]:
        """Apply additional filters to entries"""
        # This is a fallback for complex queries not handled in _query_file
        return entries

    def _sort_entries(self, entries: list[LogEntry], query: LogQuery) -> list[LogEntry]:
        """Sort entries by specified field"""
        reverse = query.sort_order == "desc"

        if query.sort_by == "timestamp":
            return sorted(entries, key=lambda x: x.timestamp, reverse=reverse)
        elif query.sort_by == "level":
            level_order = {
                level: i
                for i, level in enumerate(
                    [
                        LogLevel.DEBUG,
                        LogLevel.INFO,
                        LogLevel.WARNING,
                        LogLevel.ERROR,
                        LogLevel.CRITICAL,
                    ]
                )
            }
            return sorted(
                entries, key=lambda x: level_order.get(x.level, 0), reverse=reverse
            )
        else:
            # Generic sorting for other fields
            return sorted(
                entries, key=lambda x: getattr(x, query.sort_by, ""), reverse=reverse
            )

    def _matches_operator(
        self, entry_value: Any, query_value: Any, operator: QueryOperator
    ) -> bool:
        """Check if entry value matches query with operator"""
        try:
            if operator == QueryOperator.EQUALS:
                return entry_value == query_value
            elif operator == QueryOperator.NOT_EQUALS:
                return entry_value != query_value
            elif operator == QueryOperator.CONTAINS:
                return query_value in str(entry_value)
            elif operator == QueryOperator.NOT_CONTAINS:
                return query_value not in str(entry_value)
            elif operator == QueryOperator.GREATER_THAN:
                return entry_value > query_value
            elif operator == QueryOperator.LESS_THAN:
                return entry_value < query_value
            elif operator == QueryOperator.GREATER_EQUAL:
                return entry_value >= query_value
            elif operator == QueryOperator.LESS_EQUAL:
                return entry_value <= query_value
            elif operator == QueryOperator.REGEX:
                return bool(re.search(query_value, str(entry_value)))
            elif operator == QueryOperator.IN:
                return entry_value in query_value
            elif operator == QueryOperator.NOT_IN:
                return entry_value not in query_value
            else:
                return False
        except Exception:
            return False

    async def _load_log_file(self, filepath: Path) -> list[LogEntry]:
        """Load log entries from file"""
        try:
            async with aiofiles.open(filepath) as f:
                data = await f.read()
                entries_data = json.loads(data)
                return [LogEntry.from_dict(entry) for entry in entries_data]
        except Exception as e:
            logging.error(f"Error loading log file {filepath}: {e}")
            return []

    async def _save_log_file(self, filepath: Path, entries: list[LogEntry]) -> None:
        """Save log entries to file"""
        try:
            entries_data = [entry.to_dict() for entry in entries]

            async with aiofiles.open(filepath, "w") as f:
                if self.compression_enabled:
                    # For now, just pretty print. Could add gzip compression
                    data = json.dumps(entries_data, indent=2)
                else:
                    data = json.dumps(entries_data)
                await f.write(data)

        except Exception as e:
            logging.error(f"Error saving log file {filepath}: {e}")
            raise

    async def _update_index(self, filename: str, entries: list[LogEntry]) -> None:
        """Update search index with new entries"""
        try:
            filepath = str(self.storage_path / filename)

            for entry in entries:
                for field in self.config["index_fields"]:
                    value = getattr(entry, field, None)
                    if value is not None:
                        value_str = str(value)

                        # Initialize index structure
                        if field not in self._index:
                            self._index[field] = {}
                        if value_str not in self._index[field]:
                            self._index[field][value_str] = []

                        # Add file to index if not already present
                        if filepath not in self._index[field][value_str]:
                            self._index[field][value_str].append(filepath)

            # Update reverse index
            self._reverse_index[filepath] = {
                "entry_count": len(entries),
                "date_range": {
                    "start": min(e.timestamp for e in entries).isoformat(),
                    "end": max(e.timestamp for e in entries).isoformat(),
                },
                "last_updated": datetime.now(UTC).isoformat(),
            }

            # Save index to disk
            await self._save_index()

        except Exception as e:
            logging.error(f"Error updating index: {e}")

    async def _load_index(self) -> None:
        """Load index from disk"""
        try:
            index_file = self.storage_path / "index.json"
            if index_file.exists():
                async with aiofiles.open(index_file) as f:
                    index_data = json.loads(await f.read())
                    self._index = index_data.get("index", {})
                    self._reverse_index = index_data.get("reverse_index", {})

        except Exception as e:
            logging.error(f"Error loading index: {e}")

    async def _save_index(self) -> None:
        """Save index to disk"""
        try:
            index_file = self.storage_path / "index.json"
            index_data = {
                "index": self._index,
                "reverse_index": self._reverse_index,
                "last_updated": datetime.now(UTC).isoformat(),
            }

            async with aiofiles.open(index_file, "w") as f:
                await f.write(json.dumps(index_data, indent=2))

        except Exception as e:
            logging.error(f"Error saving index: {e}")

    def _get_cache_key(self, query: LogQuery) -> str:
        """Generate cache key for query"""
        key_parts = [
            str(query.filters or {}),
            str(query.operators or {}),
            str(query.time_range) if query.time_range else "None",
            str(query.limit),
            str(query.offset),
            query.sort_by,
            query.sort_order,
        ]
        return "|".join(key_parts)

    async def cleanup_old_logs(self, retention_days: int | None = None) -> int:
        """Clean up old log files based on retention policy"""
        retention = retention_days or self.config["retention_days"]
        cutoff_date = datetime.now(UTC) - timedelta(days=retention)

        cleaned_count = 0
        for log_file in self.storage_path.glob("logs_*.json"):
            try:
                # Extract date from filename
                filename_parts = log_file.stem.split("_")
                if len(filename_parts) >= 2:
                    # filename could split into multiple parts if the timestamp contains an underscore
                    # e.g. 'logs_YYYYMMDD_HH' -> ['logs', 'YYYYMMDD', 'HH']
                    # join the tail parts back together to restore 'YYYYMMDD_HH'
                    file_date_str = "_".join(filename_parts[1:])  # YYYYMMDD_HH
                    file_date = datetime.strptime(file_date_str, "%Y%m%d_%H").replace(
                        tzinfo=UTC
                    )

                    if file_date < cutoff_date:
                        log_file.unlink()
                        cleaned_count += 1

                        # Remove from index
                        filepath_str = str(log_file)
                        if filepath_str in self._reverse_index:
                            del self._reverse_index[filepath_str]

                        # Remove from forward index
                        for field_index in self._index.values():
                            for value_list in field_index.values():
                                if filepath_str in value_list:
                                    value_list.remove(filepath_str)

            except Exception as e:
                logging.error(f"Error cleaning up {log_file}: {e}")

        # Save updated index
        if cleaned_count > 0:
            await self._save_index()

        return cleaned_count

    async def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics"""
        try:
            total_files = 0
            total_entries = 0
            total_size = 0

            for log_file in self.storage_path.glob("logs_*.json"):
                total_files += 1
                total_size += log_file.stat().st_size

                # Count entries (could be cached for performance)
                entries = await self._load_log_file(log_file)
                total_entries += len(entries)

            return {
                "total_files": total_files,
                "total_entries": total_entries,
                "total_size_bytes": total_size,
                "index_enabled": self.index_enabled,
                "indexed_fields": list(self._index.keys()),
                "cache_entries": len(self._query_cache),
            }

        except Exception as e:
            logging.error(f"Error getting storage stats: {e}")
            return {}


# Global storage instance
_global_storage: LogStorage | None = None


def get_log_storage(config: dict[str, Any] | None = None) -> LogStorage:
    """Get or create global log storage"""
    global _global_storage

    if _global_storage is None:
        _global_storage = LogStorage(config)

    return _global_storage


def init_log_storage(config: dict[str, Any] | None = None) -> LogStorage:
    """Initialize log storage system"""
    storage = LogStorage(config)
    global _global_storage
    _global_storage = storage
    return storage
