from fastapi.testclient import TestClient

from agents.c4ai import server


def test_health():
    client = TestClient(server.app)
    r = client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("status") == "ok"
