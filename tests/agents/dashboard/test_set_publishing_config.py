import importlib

from fastapi.testclient import TestClient


def test_set_publishing_config(monkeypatch):
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    monkeypatch.setenv("ADMIN_API_KEY", "testkey")
    db = importlib.import_module("agents.dashboard.main")
    client = TestClient(db.app)

    resp = client.post(
        "/admin/set_publishing_config",
        json={
            "require_draft_fact_check_pass_for_publish": True,
            "chief_editor_review_required": False,
        },
        headers={"Authorization": "Bearer testkey"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"


def test_set_publishing_config_denied(monkeypatch):
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    monkeypatch.setenv("ADMIN_API_KEY", "testkey")
    db = importlib.import_module("agents.dashboard.main")
    client = TestClient(db.app)

    resp = client.post(
        "/admin/set_publishing_config",
        json={"require_draft_fact_check_pass_for_publish": True},
    )
    assert resp.status_code == 401
