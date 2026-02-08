import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import (
    ALLOCATIONS,
    GPUOrchestratorEngine,
)


def make_sqlite_service():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orchestrator_jobs (
            job_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            owner_pool TEXT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL,
            last_error TEXT NULL
        )
    """)
    conn.commit()

    # Ensure leases table exists for DB-backed paths exercised in the engine
    c.execute("""
        CREATE TABLE IF NOT EXISTS orchestrator_leases (
            token TEXT PRIMARY KEY,
            agent_name TEXT,
            gpu_index INTEGER NULL,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NULL,
            last_heartbeat TIMESTAMP NULL,
            metadata TEXT NULL
        )
    """)
    conn.commit()

    class CursorWrapper:
        def __init__(self, conn):
            self._conn = conn
            self._cur = None

        def execute(self, sql, params=None):
            # sqlite doesn't support FOR UPDATE; translate %s to ? and run
            sql2 = sql.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP")
            if params is None:
                self._cur = self._conn.execute(sql2)
            else:
                self._cur = self._conn.execute(sql2, params)
            return self._cur

        @property
        def rowcount(self):
            # expose underlying sqlite3.Cursor.rowcount if present
            try:
                return self._cur.rowcount if self._cur is not None else -1
            except Exception:
                return -1

        def fetchone(self):
            return self._cur.fetchone() if self._cur is not None else None

        def fetchall(self):
            return self._cur.fetchall() if self._cur is not None else []

        def close(self):
            return None

    class MBConn:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self):
            return CursorWrapper(self._conn)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

    return SimpleNamespace(mb_conn=MBConn(conn))


def test_two_sequential_claims_one_succeeds():
    ALLOCATIONS.clear()
    svc = make_sqlite_service()
    # insert pending job
    svc.mb_conn._conn.execute(
        "INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)",
        ("jc-1", "inference_jobs", json.dumps({"foo": "bar"}), "pending", 0),
    )
    svc.mb_conn._conn.commit()

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=svc,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)

        # First claim should succeed
        res1 = engine.claim_job_and_lease("jc-1", "agent-a", min_memory_mb=0)
        assert res1.get("claimed") is True

        # Second claim should fail (job no longer pending)
        res2 = engine.claim_job_and_lease("jc-1", "agent-b", min_memory_mb=0)
        assert res2.get("claimed") is False
        assert res2.get("reason") in ("not_pending", "not_pending_or_missing")
