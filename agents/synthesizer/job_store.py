import json
import logging
import time
from typing import Any

from agents.crawler.crawler_utils import _get_conn, _normalize_row

logger = logging.getLogger(__name__)

# DDL for persistent storage (MariaDB/Postgres compatible)
DDL_CREATE = """
CREATE TABLE IF NOT EXISTS synthesizer_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(32) NOT NULL,
    result TEXT NULL,
    error TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
"""


# Simple in-memory job store for synthesizer; can be upgraded to MariaDB as needed
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


_job_store = InMemoryJobStore()


def _db_is_available() -> bool:
    try:
        with _get_conn() as conn:
            return conn is not None
    except Exception:
        return False


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
        logger.debug("Synth job store: could not ensure table exists: %s", exc)


def create_job(job_id: str) -> None:
    """Create a job row in the persistent store or fall back to memory."""
    if not _db_is_available():
        _job_store.create_job(job_id)
        return
    try:
        ensure_table_exists()
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO synthesizer_jobs (job_id, status) VALUES (%s, %s)",
                    (job_id, "pending"),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Synth job store insert failed: %s", exc)
        _job_store.create_job(job_id)


def update_status(job_id: str, status: str) -> None:
    if not _db_is_available():
        _job_store.update_status(job_id, status)
        return
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE synthesizer_jobs SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
                    (status, job_id),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Synth job store update failed: %s", exc)
        _job_store.update_status(job_id, status)


def set_result(job_id: str, result: Any) -> None:
    payload = json.dumps(result, default=str)
    if not _db_is_available():
        _job_store.set_result(job_id, result)
        return
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE synthesizer_jobs SET result = %s, status = %s, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
                    (payload, "completed", job_id),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Synth job store set_result failed: %s", exc)
        _job_store.set_result(job_id, result)


def set_error(job_id: str, error: str) -> None:
    if not _db_is_available():
        _job_store.set_error(job_id, error)
        return
    try:
        with _get_conn() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE synthesizer_jobs SET error = %s, status = %s, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s",
                    (error, "failed", job_id),
                )
                conn.commit()
            finally:
                cursor.close()
    except Exception as exc:
        logger.debug("Synth job store set_error failed: %s", exc)
        _job_store.set_error(job_id, error)


def get_job(job_id: str) -> dict[str, Any] | None:
    if not _db_is_available():
        return _job_store.get_job(job_id)
    try:
        with _get_conn() as conn:
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT * FROM synthesizer_jobs WHERE job_id = %s LIMIT 1",
                    (job_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                row = _normalize_row(row)
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
        logger.debug("Synth job store get_job failed: %s", exc)
        return _job_store.get_job(job_id)
