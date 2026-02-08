import json
from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


def make_cursor_with_rows(rows=None):
    cur = MagicMock()
    if rows is None:
        rows = []
    cur.fetchall.return_value = rows
    cur.execute = MagicMock()
    cur.close = MagicMock()
    return cur


def make_conn_with_cursor(cursor):
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.commit = MagicMock()
    conn.rollback = MagicMock()
    return conn


def test_start_and_stop_worker_pool_persists(monkeypatch):
    # Create fake DB cursor and conn
    cursor = make_cursor_with_rows([])
    mb_conn = make_conn_with_cursor(cursor)

    fake_service = MagicMock()
    fake_service.mb_conn = mb_conn

    # Patch create_database_service used by the engine to return our fake
    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)

        # Keep _spawn_pool_worker from actually starting heavy processes (no-op)
        engine._spawn_pool_worker = lambda *a, **k: None

        # Start a pool
        r = engine.start_worker_pool(
            "test_pool_1",
            "model-x",
            None,
            num_workers=2,
            hold_seconds=60,
            requestor={"user": "dev"},
            variant="fp16",
        )
        assert r["pool_id"] == "test_pool_1"
        # Verify DB insert attempted
        assert any(
            "INSERT INTO worker_pools" in str(call)
            for call in cursor.execute.call_args_list
        )

        # Stop the pool
        s = engine.stop_worker_pool("test_pool_1")
        assert s["status"] == "stopped"
        # Verify DB update attempted
        assert any(
            "UPDATE worker_pools SET status=" in str(call)
            for call in cursor.execute.call_args_list
        )


def test_rehydrate_pools_reads_db_rows(monkeypatch):
    # Prepare rows returned by DB
    fake_rows = [
        {
            "pool_id": "p1",
            "agent_name": "m1",
            "model_id": "model-a",
            "adapter": None,
            "desired_workers": 3,
            "spawned_workers": 3,
            "started_at": None,
            "status": "running",
            "hold_seconds": 120,
            "metadata": json.dumps({"variant": "fp16"}),
        }
    ]

    cursor = make_cursor_with_rows(fake_rows)
    mb_conn = make_conn_with_cursor(cursor)
    fake_service = MagicMock()
    fake_service.mb_conn = mb_conn

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        # After init, reconcile should have rehydrated _WORKER_POOLS
        assert "p1" in engine._WORKER_POOLS
        meta = engine._WORKER_POOLS["p1"]
        assert meta["model"] == "model-a"
        assert meta["num_workers"] == 3
