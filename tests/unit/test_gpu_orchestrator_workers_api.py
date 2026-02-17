import os

from fastapi.testclient import TestClient

from agents.gpu_orchestrator.main import app


def test_worker_pool_lifecycle(monkeypatch):
    # Ensure test mode so workers behave as lightweight sleepers
    monkeypatch.setenv("RE_RANKER_TEST_MODE", "1")

    # ensure admin API key is present and include in headers
    monkeypatch.setenv("ADMIN_API_KEY", "adminkey123")
    client = TestClient(app)
    headers = {"Authorization": "Bearer adminkey123"}

    # create a pool named 'testpool'
    resp = client.post(
        "/workers/pool",
        json={
            "pool_id": "testpool",
            "agent": "testpool",
            "num_workers": 1,
            "hold_seconds": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("pool_id") in ("testpool",) or data.get("status") == "started"

    # list pools and confirm testpool present
    resp = client.get("/workers/pool", headers=headers)
    assert resp.status_code == 200
    pools = resp.json()
    assert any(p["pool_id"] == "testpool" for p in pools)

    # delete pool
    # test hot-swap with a new adapter
    s = client.post(
        "/workers/pool/testpool/swap",
        params={
            "new_adapter": "modelstore/agents/synthesizer/adapters/mistral_synth_v2",
            "wait_seconds": 1,
        },
        headers=headers,
    )
    assert s.status_code == 200
    assert s.json().get("status") == "swapped"

    d = client.delete("/workers/pool/testpool", headers=headers)
    assert d.status_code == 200
    assert d.json().get("status") == "stopped"

    # audit file should be created in logs/audit - test that an entry exists
    audit_file = "logs/audit/gpu_orchestrator_worker_pools.jsonl"
    assert os.path.exists(audit_file)
    with open(audit_file) as f:
        lines = f.read().strip().splitlines()
    assert any("testpool" in line for line in lines)
