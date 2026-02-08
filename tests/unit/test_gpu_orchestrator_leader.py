from unittest.mock import MagicMock, patch

from agents.gpu_orchestrator.gpu_orchestrator_engine import GPUOrchestratorEngine


class FakeCursor:
    def __init__(self):
        self.last_query = None

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        q = (self.last_query or "").upper()
        if "GET_LOCK" in q:
            return (1,)
        if "RELEASE_LOCK" in q:
            return (1,)
        # default
        return (1,)

    def close(self):
        pass


def test_try_acquire_and_release_leader(monkeypatch):
    fake_cursor = FakeCursor()
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor

    fake_service = MagicMock()
    fake_service.mb_conn = fake_conn

    with patch(
        "agents.gpu_orchestrator.gpu_orchestrator_engine.create_database_service",
        return_value=fake_service,
    ):
        engine = GPUOrchestratorEngine(bootstrap_external_services=True)
        ok = engine.try_acquire_leader_lock(timeout=1)
        assert ok is True
        assert engine.is_leader is True

        released = engine.release_leader_lock()
        assert released is True
        assert engine.is_leader is False
