"""Simple paywall aggregator backed by SQLite.

This module provides a tiny, safe counter to aggregate paywall detections
per-domain and only consider a domain "confirmed" paywalled once a
threshold is reached. It's intentionally small and dependency-free so the
server can use it without extra infra.

Usage:
    from agents.crawler.paywall_aggregator import increment_and_check
    count, reached = increment_and_check('example.com', threshold=3)

The DB path can be overridden with the env var `CRAWL4AI_PAYWALL_AGG_DB`.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time

_LOCK = threading.Lock()


def _db_path() -> str:
    return os.getenv("CRAWL4AI_PAYWALL_AGG_DB") or os.path.join(
        os.getcwd(), "model_store", "paywall_aggregator.db"
    )


def _ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS paywall_counts (
            domain TEXT PRIMARY KEY,
            count INTEGER NOT NULL,
            last_ts INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def increment_and_check(domain: str, threshold: int = 3) -> tuple[int, bool]:
    """Increment detection count for domain and return (count, reached).

    Thread-safe. Creates DB file if missing. Returns True for reached when
    count >= threshold.
    """
    if not domain:
        raise ValueError("domain is required")

    path = _db_path()
    dirpath = os.path.dirname(path)
    if dirpath and not os.path.exists(dirpath):
        try:
            os.makedirs(dirpath, exist_ok=True)
        except Exception:
            # best-effort; proceed and let sqlite raise if needed
            pass

    with _LOCK:
        conn = sqlite3.connect(path, timeout=5)
        try:
            _ensure_db(conn)
            cur = conn.execute(
                "SELECT count FROM paywall_counts WHERE domain = ?", (domain,)
            )
            row = cur.fetchone()
            if row is None:
                count = 1
                conn.execute(
                    "INSERT INTO paywall_counts(domain, count, last_ts) VALUES(?,?,?)",
                    (domain, count, int(time.time())),
                )
            else:
                count = int(row[0]) + 1
                conn.execute(
                    "UPDATE paywall_counts SET count = ?, last_ts = ? WHERE domain = ?",
                    (count, int(time.time()), domain),
                )
            conn.commit()
        finally:
            conn.close()

    return count, (count >= int(threshold))


def reset_counts(path: str | None = None) -> None:
    """Helper for tests: remove DB file if exists (best-effort)."""
    p = path or _db_path()
    try:
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass
