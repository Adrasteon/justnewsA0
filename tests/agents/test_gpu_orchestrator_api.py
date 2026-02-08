from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from agents.gpu_orchestrator import main as orchestrator_main


def test_lease_heartbeat_endpoint():
    client = TestClient(orchestrator_main.app)

    # Patch the engine heartbeat method to succeed
    with patch.object(
        orchestrator_main.engine, "heartbeat_lease", return_value=True
    ) as phb:
        r = client.post("/leases/dummy-token/heartbeat")
        assert r.status_code == 200
        assert r.json().get("heartbeat") is True
        phb.assert_called_once_with("dummy-token")


def test_list_leases_admin(monkeypatch):
    client = TestClient(orchestrator_main.app)

    # Prepare engine.get_allocations and a fake persisted row
    with patch.object(
        orchestrator_main.engine, "get_allocations", return_value={"allocations": {}}
    ):
        fake_cursor = MagicMock()
        fake_cursor.fetchall.return_value = [{"token": "t1", "agent_name": "a1"}]
        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor
        # Patch engine.db_service to use fake connection
        monkeypatch.setenv("ADMIN_API_KEY", "secret")
        orchestrator_main.engine.db_service = MagicMock()
        orchestrator_main.engine.db_service.mb_conn = fake_conn

        r = client.get("/leases", headers={"X-Admin-API-Key": "secret"})
        assert r.status_code == 200
        body = r.json()
        assert "in_memory" in body and "persistent" in body
        assert body["persistent"][0]["token"] == "t1"
