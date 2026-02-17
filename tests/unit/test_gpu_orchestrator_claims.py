from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import (
    ALLOCATIONS,
    GPUOrchestratorEngine,
)


def make_cursor_with_status(status_val):
    cursor = MagicMock()
    # For SELECT ... FOR UPDATE we'll return tuple with status
    cursor.fetchone.side_effect = [(status_val,)]
    return cursor


def test_claim_job_and_lease_success(monkeypatch):
    # Ensure ALLOCATIONS reset
    ALLOCATIONS.clear()

    cursor = make_cursor_with_status("pending")
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)

        res = engine.claim_job_and_lease("job-123", "agent-test", min_memory_mb=0)

        assert res.get("claimed") is True
        token = res.get("token")
        assert token in ALLOCATIONS

        # Ensure DB interactions performed a status check and eventually committed.
        assert cursor.fetchone.called  # status was inspected before claiming
        assert conn.commit.called


def test_claim_job_and_lease_already_claimed(monkeypatch):
    cursor = make_cursor_with_status("claimed")
    conn = MagicMock()
    conn.cursor.return_value = cursor

    fake_service = MagicMock()
    fake_service.mb_conn = conn

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        res = engine.claim_job_and_lease("job-xyz", "agent-test")

        assert res.get("claimed") is False
        assert res.get("reason") == "not_pending"
        # No commit should be attempted when not pending and DB cursor should have been consulted.
        assert cursor.fetchone.called
        assert not conn.commit.called
