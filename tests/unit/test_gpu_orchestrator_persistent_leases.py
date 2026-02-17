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


@patch("chromadb.HttpClient", return_value=MagicMock())
@patch("mysql.connector.connect", return_value=MagicMock())
def test_persist_lease_and_heartbeat(mock_mysql, mock_chroma, monkeypatch):
    # Arrange: make database cursor that records SQL statements
    cursor = make_fake_db_cursor()
    mb_conn = make_fake_mb_conn(cursor)

    # Patch create_database_service to return an object with mb_conn
    fake_service = MagicMock()
    fake_service.mb_conn = mb_conn

    # patch the symbol used by the orchestrator engine module directly
    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)

        # Force allocation to succeed deterministically
        engine._allocate_gpu = lambda req: (True, 0)

        # Act: create lease
        resp = engine.lease_gpu("test-agent", 0)
        assert resp.get("granted") is True
        token = resp.get("token")
        assert token in ALLOCATIONS

        # Verify DB insert called
        assert any(
            "INSERT INTO orchestrator_leases" in str(call)
            for call in cursor.execute.call_args_list
        )

        # Act: heartbeat
        ok = engine.heartbeat_lease(token)
        assert ok is True
        # Verify that heartbeat updated DB
        assert any(
            "UPDATE orchestrator_leases SET last_heartbeat" in str(call)
            for call in cursor.execute.call_args_list
        )

        # Act: release
        out = engine.release_gpu_lease(token)
        assert out["released"] is True
        assert token not in ALLOCATIONS
        # Verify DB delete executed
        assert any(
            "DELETE FROM orchestrator_leases" in str(call)
            for call in cursor.execute.call_args_list
        )
