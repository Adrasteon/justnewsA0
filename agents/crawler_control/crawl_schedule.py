"""Utilities for loading and evaluating the Stage B1 crawl schedule.

This module centralises validation and runtime helper logic for the
`config/crawl_schedule.yaml` file. The scheduler script imports these types
so that the governance metadata can be inspected without duplicating YAML
parsing logic across different entry-points.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


@dataclass(frozen=True)
class CrawlCadence:
    """Execution cadence for a crawl run."""

    every_hours: int = 1
    minute_offset: int = 0

    def scheduled_window_start(self, reference: datetime) -> datetime:
        """Return the start of the scheduling window anchored to the given reference."""
        base = reference.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        return base

    def scheduled_start(self, reference: datetime) -> datetime:
        """Return the precise timestamp when the run is expected to fire."""
        window_start = self.scheduled_window_start(reference)
        return window_start + timedelta(minutes=self.minute_offset)

    def is_due(self, reference: datetime) -> bool:
        """Determine whether this run should execute for the current reference window."""
        if self.every_hours <= 0:
            return True
        window_start = self.scheduled_window_start(reference)
        hour = window_start.hour
        return hour % self.every_hours == 0


@dataclass(frozen=True)
class GlobalScheduleConfig:
    """Global defaults and governance values for the crawl scheduler."""

    target_articles_per_hour: int = 500
    default_max_articles_per_site: int = 25
    default_concurrent_sites: int = 3
    default_timeout_seconds: int = 480
    strategy: str = "auto"
    enable_ai_enrichment: bool = True
    governance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawlRun:
    """Configuration for a single crawl batch."""

    name: str
    domains: list[str]
    cadence: CrawlCadence
    enabled: bool = True
    priority: int = 100
    max_articles_per_site: int | None = None
    concurrent_sites: int | None = None
    notes: str | None = None

    def scheduled_start(self, reference: datetime) -> datetime:
        return self.cadence.scheduled_start(reference)


@dataclass(frozen=True)
class CrawlSchedule:
    """Root schedule definition loaded from YAML."""

    version: int
    metadata: dict[str, Any]
    global_config: GlobalScheduleConfig
    runs: list[CrawlRun]

    def due_runs(self, reference: datetime) -> list[CrawlRun]:
        """Return runs that are enabled and due for the provided reference time."""
        eligible: list[CrawlRun] = []
        for run in self.runs:
            if not run.enabled:
                continue
            if run.cadence.is_due(reference):
                eligible.append(run)
        # Order by priority, minute offset, then name for deterministic execution
        eligible.sort(key=lambda r: (r.priority, r.cadence.minute_offset, r.name))
        return eligible

    @property
    def governance(self) -> dict[str, Any]:
        return self.global_config.governance


class CrawlScheduleError(RuntimeError):
    """Raised when the crawl schedule cannot be parsed or validated."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise CrawlScheduleError(f"Unable to open crawl schedule: {path}") from exc
    except yaml.YAMLError as exc:
        raise CrawlScheduleError(f"Invalid crawl schedule YAML: {path}") from exc

    if not isinstance(raw, dict):
        raise CrawlScheduleError("Crawl schedule root must be a mapping")
    return raw


def _parse_cadence(data: dict[str, Any]) -> CrawlCadence:
    every_hours = int(data.get("every_hours", 1) or 1)
    minute_offset = int(data.get("minute_offset", 0) or 0)
    if every_hours < 0:
        raise CrawlScheduleError("cadence.every_hours must be >= 0")
    if not 0 <= minute_offset < 60:
        raise CrawlScheduleError("cadence.minute_offset must be between 0 and 59")
    return CrawlCadence(every_hours=every_hours, minute_offset=minute_offset)


def _parse_run(item: dict[str, Any], defaults: GlobalScheduleConfig) -> CrawlRun:
    name = item.get("name")
    if not name:
        raise CrawlScheduleError("Each run requires a name")

    domains = item.get("domains") or []
    if not isinstance(domains, Iterable) or not all(domains):
        raise CrawlScheduleError(f"Run '{name}' must declare at least one domain")
    domains = [str(domain).strip() for domain in domains if str(domain).strip()]

    cadence_data = item.get("cadence", {})
    if not isinstance(cadence_data, dict):
        raise CrawlScheduleError(f"Run '{name}' cadence must be a mapping")
    cadence = _parse_cadence(cadence_data)

    priority = int(item.get("priority", 100))
    max_articles = item.get(
        "max_articles_per_site", defaults.default_max_articles_per_site
    )
    concurrent_sites = item.get("concurrent_sites", defaults.default_concurrent_sites)

    return CrawlRun(
        name=name,
        domains=domains,
        cadence=cadence,
        enabled=bool(item.get("enabled", True)),
        priority=priority,
        max_articles_per_site=int(max_articles),
        concurrent_sites=int(concurrent_sites),
        notes=item.get("notes"),
    )


def load_crawl_schedule(path: Path) -> CrawlSchedule:
    """Load and validate the crawl schedule from YAML."""
    raw = _load_yaml(path)

    version = int(raw.get("version", 1))
    metadata = raw.get("metadata") or {}
    global_data = raw.get("global") or {}

    defaults = GlobalScheduleConfig(
        target_articles_per_hour=int(global_data.get("target_articles_per_hour", 500)),
        default_max_articles_per_site=int(
            global_data.get("default_max_articles_per_site", 25)
        ),
        default_concurrent_sites=int(global_data.get("default_concurrent_sites", 3)),
        default_timeout_seconds=int(global_data.get("default_timeout_seconds", 480)),
        strategy=str(global_data.get("strategy", "auto")),
        enable_ai_enrichment=bool(global_data.get("enable_ai_enrichment", True)),
        governance=global_data.get("governance", {}) or {},
    )

    run_items = raw.get("runs") or []
    if not isinstance(run_items, list) or not run_items:
        raise CrawlScheduleError("Crawl schedule must contain at least one run entry")

    runs = [_parse_run(item, defaults) for item in run_items]

    return CrawlSchedule(
        version=version,
        metadata=metadata,
        global_config=defaults,
        runs=runs,
    )


def _normalize_domain_from_source(source: dict[str, Any]) -> str | None:
    """Best-effort extraction of a domain from a database source row."""
    raw_domain = str(source.get("domain") or "").strip()
    if raw_domain:
        parsed = urlparse(raw_domain)
        domain = parsed.netloc or parsed.path or raw_domain
        return domain.lower() or None

    raw_url = str(source.get("url") or "").strip()
    if not raw_url:
        return None
    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    if not parsed.netloc:
        return None
    return parsed.netloc.lower()


def load_crawl_schedule_from_sources(
    sources: Iterable[dict[str, Any]],
    *,
    chunk_size: int = 10,
    metadata: dict[str, Any] | None = None,
    global_overrides: dict[str, Any] | None = None,
) -> CrawlSchedule:
    """Build a crawl schedule dynamically from database sources."""

    if chunk_size <= 0:
        raise CrawlScheduleError("chunk_size must be greater than zero")

    seen: set[str] = set()
    domains: list[str] = []
    for source in sources:
        domain = _normalize_domain_from_source(source or {})
        if not domain or domain in seen:
            continue
        seen.add(domain)
        domains.append(domain)

    if not domains:
        raise CrawlScheduleError("No crawlable domains discovered in sources dataset")

    domains.sort()

    overrides = global_overrides or {}
    global_config = GlobalScheduleConfig(
        target_articles_per_hour=int(overrides.get("target_articles_per_hour", 500)),
        default_max_articles_per_site=int(
            overrides.get("default_max_articles_per_site", 25)
        ),
        default_concurrent_sites=int(overrides.get("default_concurrent_sites", 3)),
        default_timeout_seconds=int(overrides.get("default_timeout_seconds", 480)),
        strategy=str(overrides.get("strategy", "auto")),
        enable_ai_enrichment=bool(overrides.get("enable_ai_enrichment", True)),
        governance=overrides.get("governance", {}) or {},
    )

    runs: list[CrawlRun] = []
    num_runs = max(1, (len(domains) + chunk_size - 1) // chunk_size)
    minute_step = max(1, 60 // num_runs)
    for index in range(0, len(domains), chunk_size):
        chunk = domains[index : index + chunk_size]
        cadence = CrawlCadence(
            every_hours=1, minute_offset=(index // chunk_size * minute_step) % 60
        )
        run = CrawlRun(
            name=f"database_sources_{index // chunk_size + 1}",
            domains=chunk,
            cadence=cadence,
            enabled=True,
            priority=index // chunk_size + 1,
            max_articles_per_site=global_config.default_max_articles_per_site,
            concurrent_sites=global_config.default_concurrent_sites,
            notes="Generated from sources table",
        )
        runs.append(run)

    schedule_metadata = metadata or {}
    combined_metadata = {
        "description": "Generated from database sources",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    combined_metadata.update(schedule_metadata)

    return CrawlSchedule(
        version=1,
        metadata=combined_metadata,
        global_config=global_config,
        runs=runs,
    )


__all__ = [
    "CrawlCadence",
    "CrawlRun",
    "CrawlSchedule",
    "CrawlScheduleError",
    "GlobalScheduleConfig",
    "load_crawl_schedule",
    "load_crawl_schedule_from_sources",
]
