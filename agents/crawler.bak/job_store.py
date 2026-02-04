"""Persistent job storage for the crawler agent.

Provides a thin wrapper around MariaDB storage for crawl job lifecycle
information while also falling back to an in-memory store when the database
is unavailable (e.g. in development or test envs).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .crawler_utils import _get_conn, _normalize_row

logger = logging.getLogger(__name__)

DDL_CREATE = """
CREATE TABLE IF NOT EXISTS crawler_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    result TEXT NULL,
    error TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""


def ensure_table_exists() -> None:
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(DDL_CREATE)
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store: could not ensure table exists: %s", exc)


class InMemoryJobStore:
    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}

    def create_job(self, job_id: str, status: str = "pending") -> None:
        self._store[job_id] = {
            "job_id": job_id,
            "status": status,
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def update_status(self, job_id: str, status: str) -> None:
        job = self._store.setdefault(job_id, {})
        job["status"] = status
        job["updated_at"] = time.time()

    def set_result(self, job_id: str, result: Any) -> None:
        job = self._store.setdefault(job_id, {})
        job["result"] = result
        job["status"] = "completed"
        job["updated_at"] = time.time()

    def set_error(self, job_id: str, error: str) -> None:
        job = self._store.setdefault(job_id, {})
        job["error"] = error
        job["status"] = "failed"
        job["updated_at"] = time.time()

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self._store.get(job_id)

    def list_jobs(self) -> dict[str, str]:
        return {job_id: job.get("status") for job_id, job in self._store.items()}


_in_memory_store = InMemoryJobStore()


def _db_is_available() -> bool:
    try:
        with _get_conn() as conn:
            return conn is not None
    except Exception:
        return False


def create_job(job_id: str, status: str = "pending") -> None:
    """Create a job row in the persistent store or fall back to memory."""
    if not _db_is_available():
        _in_memory_store.create_job(job_id, status)
        return
    try:
        ensure_table_exists()
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO crawler_jobs (job_id, status) VALUES (%s, %s)",
                    (job_id, status),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store insert failed: %s", exc)
        _in_memory_store.create_job(job_id, status)


def update_status(job_id: str, status: str) -> None:
    if not _db_is_available():
        _in_memory_store.update_status(job_id, status)
        return
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE crawler_jobs SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
                    (status, job_id),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store update failed: %s", exc)
        _in_memory_store.update_status(job_id, status)


def set_result(job_id: str, result: Any) -> None:
    payload = json.dumps(result, default=str)
    if not _db_is_available():
        _in_memory_store.set_result(job_id, result)
        return
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE crawler_jobs SET result = %s, status = %s, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
                    (payload, "completed", job_id),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store set_result failed: %s", exc)
        _in_memory_store.set_result(job_id, result)


def set_error(job_id: str, error: str) -> None:
    if not _db_is_available():
        _in_memory_store.set_error(job_id, error)
        return
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE crawler_jobs SET error = %s, status = %s, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
                    (error, "failed", job_id),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store set_error failed: %s", exc)
        _in_memory_store.set_error(job_id, error)


def get_job(job_id: str) -> dict[str, Any] | None:
    if not _db_is_available():
        return _in_memory_store.get_job(job_id)
    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT * FROM crawler_jobs WHERE job_id = %s LIMIT 1", (job_id,)
                )
                row = cursor.fetchone()
                if not row:
                    return None
                row = _normalize_row(row)
                # Deserialize result
                if row.get("result"):
                    try:
                        row["result"] = (
                            json.loads(row["result"])
                            if isinstance(row["result"], str)
                            else row["result"]
                        )
                    except Exception:
                        pass
                return row
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store get_job failed: %s", exc)
        return _in_memory_store.get_job(job_id)


def list_jobs() -> dict[str, str]:
    if not _db_is_available():
        return _in_memory_store.list_jobs()
    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT job_id, status FROM crawler_jobs ORDER BY updated_at DESC"
                )
                rows = cursor.fetchall()
                return {row["job_id"]: row["status"] for row in rows}
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store list_jobs failed: %s", exc)
        return _in_memory_store.list_jobs()


def recover_running_jobs(markdown_reason: str = "service restart") -> int:
    """Mark any jobs with status 'running' as 'failed' due to service restart.

    Returns number of recovered jobs updated.
    """
    updated = 0
    if not _db_is_available():
        # In-memory fallback: scan and update
        for job_id, job in list(_in_memory_store._store.items()):
            if job.get("status") == "running":
                _in_memory_store.set_error(job_id, f"interrupted: {markdown_reason}")
                updated += 1
        return updated
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT job_id FROM crawler_jobs WHERE status = %s", ("running",)
                )
                rows = cursor.fetchall()
                for (job_id,) in rows:
                    cursor.execute(
                        "UPDATE crawler_jobs SET status = %s, error = %s, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
                        ("failed", f"interrupted: {markdown_reason}", job_id),
                    )
                    updated += 1
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store recover_running_jobs failed: %s", exc)
    return updated


def clear_all() -> int:
    """Clear all jobs from the persistent store or in-memory fallback.

    Returns number of jobs removed (best-effort).
    """
    if not _db_is_available():
        count = len(_in_memory_store._store)
        _in_memory_store._store.clear()
        return count
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT COUNT(*) FROM crawler_jobs")
                total = cursor.fetchone()[0] or 0
                cursor.execute("DELETE FROM crawler_jobs")
                conn.commit()
                return int(total)
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Job store clear_all failed: %s", exc)
        # Fallback to in-memory clear
        count = len(_in_memory_store._store)
        _in_memory_store._store.clear()
        return count
