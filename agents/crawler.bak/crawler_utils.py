"""Utility helpers for the simplified crawler stack.

The original system relied on a deep graph of database and browser utilities
that were removed during the repository clean-up. This lightweight module
reintroduces the minimal surface area required by ``crawler_engine`` so the
service can boot and perform basic work. Database calls are best-effort: when
the MariaDB backend is unavailable the helpers fall back to safe defaults and
emit structured log messages rather than raising fatal exceptions. Legacy
PostgreSQL environment variables are still honoured for compatibility during
the transition period.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import mysql.connector
from mysql.connector import pooling

from common.env_loader import load_global_env
from common.observability import get_logger

logger = get_logger(__name__)

# Ensure MariaDB credentials from global.env are available when running ad-hoc scripts
load_global_env(logger=logger)

_POOL_LOCK = threading.Lock()
_CONNECTION_POOL: pooling.MySQLConnectionPool | None = None


def _env(name: str, default: str | None = None) -> str | None:
    """Fetch an environment variable using uppercase or lowercase keys."""

    return os.environ.get(name) or os.environ.get(name.lower(), default)


def _db_config() -> dict[str, Any]:
    """Return database connection details with MariaDB defaults."""

    host = _env("MARIADB_HOST", "localhost")
    port = int(_env("MARIADB_PORT", "3306"))
    database = _env("MARIADB_DB", "justnews")
    user = _env("MARIADB_USER", "justnews_user")
    password = _env("MARIADB_PASSWORD", "")
    charset = _env("MARIADB_CHARSET", "utf8mb4")

    return {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
        "charset": charset,
        "use_pure": True,
    }


def initialize_connection_pool(
    minconn: int | None = None, maxconn: int | None = None
) -> None:
    """Initialise a thread-safe MariaDB connection pool."""

    global _CONNECTION_POOL
    if _CONNECTION_POOL:
        return
    with _POOL_LOCK:
        if _CONNECTION_POOL:
            return

        db_config = _db_config()
        min_conn = minconn or int(_env("DB_POOL_MIN_CONNECTIONS", "1"))
        max_conn = maxconn or int(_env("DB_POOL_MAX_CONNECTIONS", "4"))
        pool_size = max(1, max(min_conn, max_conn))

        try:
            _CONNECTION_POOL = pooling.MySQLConnectionPool(
                pool_name="crawler_pool",
                pool_size=pool_size,
                **db_config,
            )
            logger.info("Created MariaDB connection pool (size=%s)", pool_size)
        except mysql.connector.Error as exc:  # pragma: no cover - defensive
            logger.warning("Failed to create MariaDB connection pool: %s", exc)
            _CONNECTION_POOL = None


@contextmanager
def _get_conn():
    conn = None
    try:
        if _CONNECTION_POOL:
            conn = _CONNECTION_POOL.get_connection()
        else:
            conn = mysql.connector.connect(**_db_config())
        yield conn
    except mysql.connector.Error as exc:  # pragma: no cover - defensive
        logger.warning("Database operation failed: %s", exc)
        raise
    finally:
        if conn is not None:
            conn.close()


def create_crawling_performance_table() -> None:
    """Ensure the crawler performance table exists (no-op on failure)."""
    ddl = """
    CREATE TABLE IF NOT EXISTS crawler_performance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        source_id BIGINT NULL,
        domain VARCHAR(255),
        strategy_used VARCHAR(255) NOT NULL,
        articles_processed INT NOT NULL,
        articles_per_second DOUBLE NOT NULL,
        duration_seconds DOUBLE NOT NULL,
        crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(ddl)
                conn.commit()
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug(
            "Skipping crawler_performance table creation (database unavailable)"
        )


@dataclass
class CanonicalMetadata:
    """Reusable structure for canonical article hints."""

    url: str
    title: str | None = None
    published_at: datetime | None = None


class RateLimiter:
    """Simple token bucket per domain to prevent hammering a site."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._records: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def acquire(self, domain: str) -> None:
        with self._lock:
            bucket = self._records.setdefault(domain, deque())
            now = time.monotonic()
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                sleep_for = self.window_seconds - (now - bucket[0])
                logger.debug("Rate limiter sleeping %.2fs for %s", sleep_for, domain)
                time.sleep(max(0.0, sleep_for))
            bucket.append(time.monotonic())


class RobotsChecker:
    """Robots.txt checker with per-host TTL-cached parser.

    Uses the stdlib ``urllib.robotparser.RobotFileParser`` implementation and
    caches per-domain robots.txt parser instances for a configurable TTL to
    avoid fetching robots.txt on every request. If the fetch fails, the
    behaviour depends on the ``CRAWLER_ROBOTS_FALLBACK`` env value (allow or
    deny); default is to ``allow`` to avoid mistakenly blocking sites in
    environments with transient network issues.
    """

    def __init__(self, ttl_seconds: int | None = None, user_agent: str | None = None):
        import urllib.robotparser

        self._robot_parser_class = urllib.robotparser.RobotFileParser
        self._cache: dict[str, tuple[urllib.robotparser.RobotFileParser, float]] = {}
        self._ttl = int(
            ttl_seconds
            if ttl_seconds is not None
            else int(os.environ.get("CRAWLER_ROBOTS_TTL", "86400"))
        )
        self._user_agent = user_agent or os.environ.get(
            "CRAWLER_ROBOTS_USER_AGENT", "JustNewsCrawler"
        )
        self._fetch_fallback = os.environ.get(
            "CRAWLER_ROBOTS_FALLBACK", "allow"
        ).lower()

    def _get_parser_for_domain(self, domain: str):
        entry = self._cache.get(domain)
        now_ts = time.time()
        if entry and entry[1] > now_ts:
            return entry[0]
        parser = self._robot_parser_class()
        urls_to_try = [f"https://{domain}/robots.txt", f"http://{domain}/robots.txt"]
        for url in urls_to_try:
            try:
                parser.set_url(url)
                parser.read()
                # Successful read, cache and return
                self._cache[domain] = (parser, now_ts + self._ttl)
                return parser
            except Exception as e:
                logger.debug("Failed to fetch robots.txt from %s: %s", url, e)
                continue
        # On failure, create a parser that is permissive or restrictive based on config
        if self._fetch_fallback == "deny":
            # Create fake parser that denies everything
            fake = self._robot_parser_class()
            fake.parse(["User-agent: *", "Disallow: /"])
        else:
            # default allow all
            fake = self._robot_parser_class()
            fake.parse(["User-agent: *", "Disallow: "])
        self._cache[domain] = (fake, now_ts + self._ttl)
        return fake

    def is_allowed(self, url: str) -> bool:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc
            if not domain:
                return True
            parser = self._get_parser_for_domain(domain)
            return parser.can_fetch(self._user_agent, url)
        except Exception as e:
            logger.debug("RobotsChecker.is_allowed failed: %s", e)
            # Default to allow to avoid accidental global blocking
            return True


class ModalDismisser:
    """Placeholder for modal-handling logic used by Playwright crawlers."""

    async def dismiss(self, page: Any) -> None:  # pragma: no cover - async placeholder
        return


def _maybe_json(value: Any, default: Any = None) -> Any:
    """Attempt to decode JSON values, returning the original on failure."""

    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "ignore")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default if default is not None else value
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value if value is not None else default


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalise database rows to plain Python types."""

    normalised: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            normalised[key] = float(value)
        elif key == "metadata":
            normalised[key] = _maybe_json(value, {})
        elif isinstance(value, (bytes, bytearray)):
            normalised[key] = value.decode("utf-8", "ignore")
        else:
            normalised[key] = value
    return normalised


def get_active_sources(
    limit: int | None = None,
    *,
    include_paywalled: bool = False,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    if not include_paywalled:
        conditions.append("COALESCE(paywall, 0) = 0")

    sql = "SELECT * FROM sources"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY last_verified IS NULL, last_verified DESC"

    params: tuple[Any, ...] = ()
    if limit is not None:
        sql += " LIMIT %s"
        params = (limit,)
    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [_normalize_row(row) for row in rows]
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug("Falling back to empty active sources list")
        return []


def get_sources_by_domain(domains: Iterable[str]) -> list[dict[str, Any]]:
    domain_list = [d.lower() for d in domains if d]
    if not domain_list:
        return []
    placeholders = ", ".join(["%s"] * len(domain_list))
    sql = f"SELECT * FROM sources WHERE LOWER(domain) IN ({placeholders})"
    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(sql, tuple(domain_list))
                rows = cursor.fetchall()
                return [_normalize_row(row) for row in rows]
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug("Could not fetch sources for domains: %s", domain_list)
        return []


def update_source_crawling_strategy(source_id: int, strategy: str) -> None:
    sql = (
        "UPDATE sources SET metadata = JSON_SET(COALESCE(metadata, JSON_OBJECT()), '$.crawling_strategy', %s),"
        " updated_at = NOW() WHERE id = %s"
    )
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(sql, (strategy, source_id))
                conn.commit()
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug("Failed to persist crawling strategy for source_id=%s", source_id)


def record_crawling_performance(
    *,
    source_id: int | None,
    domain: str | None,
    strategy_used: str,
    articles_processed: int,
    duration_seconds: float,
) -> None:
    if duration_seconds <= 0:
        duration_seconds = 1e-6
    articles_per_second = articles_processed / duration_seconds
    sql = (
        "INSERT INTO crawler_performance (source_id, domain, strategy_used, articles_processed, articles_per_second, duration_seconds)"
        " VALUES (%s, %s, %s, %s, %s, %s)"
    )
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    sql,
                    (
                        source_id,
                        domain,
                        strategy_used,
                        articles_processed,
                        articles_per_second,
                        duration_seconds,
                    ),
                )
                conn.commit()
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug(
            "Could not record crawling performance for %s", domain or source_id
        )


def record_paywall_detection(
    *,
    source_id: int | None = None,
    domain: str | None = None,
    skip_count: int,
    threshold: int,
    paywall_type: str | None = "hard",
) -> bool:
    """Persist paywall skip telemetry and flag the source when the threshold is reached.

    Returns True when the paywall flag transitions from false to true.
    """

    if skip_count <= 0:
        return False
    identifier: tuple[str, tuple[Any, ...]] | None = None
    if source_id is not None:
        identifier = ("id = %s", (source_id,))
    elif domain:
        identifier = ("LOWER(domain) = %s", (domain.lower(),))

    if identifier is None:
        return False

    where_clause, where_params = identifier

    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    f"SELECT id, domain, paywall, paywall_type, metadata FROM sources WHERE {where_clause} LIMIT 1",
                    where_params,
                )
                row = cursor.fetchone()
                if not row:
                    return False

                metadata_raw = row.get("metadata")
                metadata = _maybe_json(metadata_raw, {})
                if not isinstance(metadata, dict):
                    metadata = {}

                paywall_meta = metadata.get("paywall_detection")
                if not isinstance(paywall_meta, dict):
                    paywall_meta = {}

                existing_missed = int(paywall_meta.get("skip_streak", 0) or 0)
                total_skips = int(paywall_meta.get("total_skips", 0) or 0)

                new_skip_streak = existing_missed + skip_count
                new_total_skips = total_skips + skip_count

                paywall_meta.update(
                    {
                        "skip_streak": new_skip_streak,
                        "total_skips": new_total_skips,
                        "last_detected_at": datetime.now(UTC).isoformat() + "Z",
                        "threshold": threshold,
                    }
                )
                metadata["paywall_detection"] = paywall_meta

                was_paywalled = bool(row.get("paywall"))
                should_flag = new_skip_streak >= max(1, threshold)
                now_paywalled = was_paywalled or should_flag

                resolved_paywall_type = row.get("paywall_type")
                if now_paywalled and not resolved_paywall_type and paywall_type:
                    resolved_paywall_type = paywall_type

                cursor.execute(
                    "UPDATE sources SET paywall = %s, paywall_type = %s, metadata = %s, updated_at = NOW() WHERE id = %s",
                    (
                        now_paywalled,
                        resolved_paywall_type,
                        json.dumps(metadata, default=str),
                        row["id"],
                    ),
                )
                conn.commit()
                return now_paywalled and not was_paywalled
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug("Failed to persist paywall detection for %s", domain or source_id)
        return False


def get_source_performance_history(
    identifier: Any, limit: int = 5
) -> list[dict[str, Any]]:
    if identifier is None:
        return []
    if isinstance(identifier, int):
        where_clause = "source_id = %s"
        params: tuple[Any, ...] = (identifier,)
    else:
        where_clause = "LOWER(domain) = %s"
        params = (str(identifier).lower(),)
    sql = (
        "SELECT source_id, domain, strategy_used, articles_processed, articles_per_second, duration_seconds, crawled_at "
        f"FROM crawler_performance WHERE {where_clause} ORDER BY crawled_at DESC LIMIT %s"
    )
    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(sql, params + (limit,))
                rows = cursor.fetchall()
                return [_normalize_row(row) for row in rows]
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug("No performance history found for %s", identifier)
        return []


def get_optimal_sources_for_strategy(
    strategy: str, limit: int = 10
) -> list[dict[str, Any]]:
    sql = (
        "SELECT source_id, domain, AVG(articles_per_second) AS avg_speed "
        "FROM crawler_performance WHERE strategy_used = %s "
        "GROUP BY source_id, domain ORDER BY avg_speed DESC LIMIT %s"
    )
    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(sql, (strategy, limit))
                rows = cursor.fetchall()
                return [_normalize_row(row) for row in rows]
            finally:
                cursor.close()
    except mysql.connector.Error:
        logger.debug("No optimal sources available for strategy %s", strategy)
        return []


__all__ = [
    "CanonicalMetadata",
    "ModalDismisser",
    "RateLimiter",
    "RobotsChecker",
    "create_crawling_performance_table",
    "get_active_sources",
    "get_optimal_sources_for_strategy",
    "get_source_performance_history",
    "get_sources_by_domain",
    "initialize_connection_pool",
    "record_crawling_performance",
    "record_paywall_detection",
    "update_source_crawling_strategy",
]
