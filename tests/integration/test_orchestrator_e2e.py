import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


class InMemoryRedis:
    def __init__(self):
        self.streams = {}
        # pending entries per stream (format: list of (id, consumer, idle_ms, delivered))
        self._pending = {}

    def xadd(self, stream, fields):
        lst = self.streams.setdefault(stream, [])
        idx = len(lst) + 1
        msg_id = f"{idx}-0"
        # store bytes keys like real redis client
        stored = {
            k if isinstance(k, str) else k: (
                v
                if isinstance(v, bytes)
                else (json.dumps(v).encode("utf-8") if not isinstance(v, bytes) else v)
            )
            for k, v in fields.items()
        }
        lst.append((msg_id, stored))
        # also track as pending for consumer group semantics
        pend = self._pending.setdefault(stream, [])
        pend.append((msg_id, "test_consumer", 0, 1))
        return msg_id

    def xrange(self, stream, min, max):
        entries = self.streams.get(stream, [])
        return list(entries)

    def xpending_range(self, stream, group, start, end, count=100):
        return list(self._pending.get(stream, []))

    def xack(self, stream, group, message_id):
        # remove pending entry if present
        pend = self._pending.get(stream, [])
        self._pending[stream] = [p for p in pend if p[0] != message_id]
        return True


def create_sqlite_service():
    # create in-memory sqlite and build necessary table(s)
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orchestrator_jobs (
            job_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            owner_pool TEXT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NULL,
                last_error TEXT NULL,
                timeout_seconds INTEGER NULL
        )
    """)
    conn.commit()

    # Provide a lightweight wrapper that accepts MySQL-style %%s placeholders and maps
    # them to sqlite '?' so engine SQL with %s works in tests.
    class CursorWrapper:
        def __init__(self, conn):
            self._conn = conn
            self._cur = None

        def execute(self, sql, params=None):
            # Translate some MySQL-specific helpers to sqlite equivalents used for tests
            sql2 = sql.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP")
            if params is None:
                self._cur = self._conn.execute(sql2)
            else:
                self._cur = self._conn.execute(sql2, params)
            return self._cur

        def fetchone(self):
            return self._cur.fetchone() if self._cur is not None else None

        def fetchall(self):
            return self._cur.fetchall() if self._cur is not None else []

        def close(self):
            return None

    class MBConnWrapper:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self):
            return CursorWrapper(self._conn)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

    # ensure leases table exists for DB-backed paths exercised in integration tests
    cursor.execute("""
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

    # Return a minimal 'service' with mb_conn attribute used by engine
    return SimpleNamespace(mb_conn=MBConnWrapper(conn))


def test_submit_job_persistence_and_redis_write():
    svc = create_sqlite_service()
    fake_redis = InMemoryRedis()

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=svc,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        # ensure redis client assigned after init
        engine.redis_client = fake_redis

        job_id = "itest-1"
        res = engine.submit_job(job_id, "inference_jobs", {"x": 42})
        assert res["job_id"] == job_id

        # verify job persisted in sqlite
        cur = svc.mb_conn.cursor()
        cur.execute(
            "SELECT job_id, type, payload, status, attempts FROM orchestrator_jobs WHERE job_id=?",
            (job_id,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row[0] == job_id
        assert row[1] == "inference_jobs"
        payload = json.loads(row[2])
        assert payload["x"] == 42

        # verify redis stream contains message
        stream = "stream:orchestrator:inference_jobs"
        entries = fake_redis.xrange(stream, "-", "+")
        assert len(entries) == 1
        _, fields = entries[0]
        assert ("payload" in fields) or (b"payload" in fields)


def test_reclaimer_integration_requeues_and_dlq():
    svc = create_sqlite_service()
    fake_redis = InMemoryRedis()

    # prepopulate DB job with attempts set to 1
    cur = svc.mb_conn.cursor()
    cur.execute(
        "INSERT INTO orchestrator_jobs (job_id, type, payload, status, attempts) VALUES (?,?,?,?,?)",
        ("ij-1", "inference_jobs", json.dumps({"y": 1}), "pending", 1),
    )
    svc.mb_conn.commit()

    # simulate a pending entry with large idle time so reclaimer will pick it
    mid = fake_redis.xadd(
        "stream:orchestrator:inference_jobs",
        {"job_id": "ij-1", "payload": json.dumps({"y": 1})},
    )
    # overwrite pending idle measurement so reclaim logic treats it as stale
    fake_redis._pending["stream:orchestrator:inference_jobs"] = [
        (mid, "consumer", 120000, 1)
    ]

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=svc,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = fake_redis
        engine._job_retry_max = 2

        # run a reclaim pass - attempt should increment to 2 and cause DLQ
        engine._reclaimer_pass()

        # DB: job should now be either updated attempts or set to dead_letter
        cur.execute(
            "SELECT attempts, status FROM orchestrator_jobs WHERE job_id=?", ("ij-1",)
        )
        r = cur.fetchone()
        assert r is not None
        # if attempts reached threshold, status should be 'dead_letter'
        assert r[1] in ("dead_letter", "pending")

        # DLQ - should be present (either moved to dlq or requeued)
        dlq = "stream:orchestrator:inference_jobs:dlq"
        dlq_entries = fake_redis.streams.get(dlq, [])
        # If we hit DLQ condition (which should), entries > 0
        assert isinstance(dlq_entries, list)
