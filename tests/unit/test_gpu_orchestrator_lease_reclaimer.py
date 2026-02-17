import json
import time
from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import (
    ALLOCATIONS,
    GPUOrchestratorEngine,
)


def make_fake_db_cursor():
    cur = MagicMock()
    cur.execute = MagicMock()
    cur.fetchall = MagicMock(return_value=[])
    cur.fetchone = MagicMock(return_value=(1,))
    cur.close = MagicMock()
    return cur


def make_fake_mb_conn(cursor):
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    return conn


def test_heartbeat_refreshes_allocation_and_prevents_purge(monkeypatch):
    cursor = make_fake_db_cursor()
    mb_conn = make_fake_mb_conn(cursor)

    fake_service = MagicMock()
    fake_service.mb_conn = mb_conn

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)

        # Force allocation success
        engine._allocate_gpu = lambda req: (True, 0)

        # Create a lease
        resp = engine.lease_gpu("hb-agent", 0)
        assert resp.get("granted") is True
        token = resp.get("token")
        assert token in ALLOCATIONS

        # Make allocation timestamp artificially old (> 1 hour)
        ALLOCATIONS[token]["timestamp"] = time.time() - (3600 + 10)

        # Purge would normally remove it
        engine._purge_expired_leases()
        assert token not in ALLOCATIONS

        # Re-create lease, then heartbeat should refresh timestamp and prevent purge
        resp = engine.lease_gpu("hb-agent", 0)
        token2 = resp.get("token")
        assert token2 in ALLOCATIONS

        # make it old again
        ALLOCATIONS[token2]["timestamp"] = time.time() - (3600 + 10)

        # heartbeat updates in-memory and DB
        ok = engine.heartbeat_lease(token2)
        assert ok is True
        # cursor.execute should contain UPDATE orchestrator_leases
        assert any(
            "UPDATE orchestrator_leases" in str(call)
            for call in cursor.execute.call_args_list
        )

        # now purge - should not remove this lease because heartbeat refreshed it
        engine._purge_expired_leases()
        assert token2 in ALLOCATIONS


def test_reclaimer_does_not_delete_lease_rows(monkeypatch):
    # Setup fake redis client with a single stale pending entry
    fake_redis = MagicMock()
    fake_redis.xpending_range.return_value = [("1-0", "consumer", 120000, 1)]
    fake_redis.xrange.return_value = [
        ("1-0", {b"job_id": b"j1", b"payload": json.dumps({"x": 1}).encode("utf-8")})
    ]
    fake_redis.xadd = MagicMock()
    fake_redis.xack = MagicMock()

    # Setup fake DB: orchestrator_jobs will be present and attempts will be below max
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(1,)]  # attempts currently = 1
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        engine.redis_client = fake_redis
        # set low retry max so we can exercise path
        engine._job_retry_max = 2

        # Ensure there is an active lease in ALLOCATIONS and DB -- reclaimer shouldn't touch it
        engine._allocate_gpu = lambda req: (True, 0)
        resp = engine.lease_gpu("r-agent", 0)
        _token = resp.get("token")

        # Reset cursor call history
        cursor.execute.reset_mock()

        # Run reclaimer pass
        engine._reclaimer_pass()

        # Reclaimer should update orchestrator_jobs (attempts increment / requeue) but should not delete leases
        executed_sqls = [
            c[0][0] for c in conn.cursor.return_value.execute.call_args_list
        ]
        # executed_sqls captures SQL statements invoked against DB during reclaimer pass
        assert any("orchestrator_jobs" in sql for sql in executed_sqls)
        # Ensure no DELETE FROM orchestrator_leases was called
        assert not any(
            "DELETE FROM orchestrator_leases" in sql for sql in executed_sqls
        )
