from unittest.mock import patch

from fastapi.testclient import TestClient

from agents.gpu_orchestrator import main as orchestrator_main


def test_get_leader_endpoint():
    client = TestClient(orchestrator_main.app)
    with (
        patch.object(orchestrator_main.engine, "is_leader", True),
        patch.object(
            orchestrator_main.engine, "_leader_lock_name", "gpu_orchestrator_leader"
        ),
    ):
        r = client.get("/leader")
        assert r.status_code == 200
        body = r.json()
        assert body.get("is_leader") is True
        assert body.get("lock_name") == "gpu_orchestrator_leader"
