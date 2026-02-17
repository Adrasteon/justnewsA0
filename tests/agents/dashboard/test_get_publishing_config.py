import importlib

from fastapi.testclient import TestClient


def test_get_publishing_config(monkeypatch):
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    monkeypatch.setenv("ADMIN_API_KEY", "testkey")
    db = importlib.import_module("agents.dashboard.main")
    client = TestClient(db.app)

    resp = client.get(
        "/admin/get_publishing_config", headers={"Authorization": "Bearer testkey"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "require_draft_fact_check_pass_for_publish" in data
    assert "chief_editor_review_required" in data
    assert "synthesized_article_storage" in data


def test_get_publishing_config_denied(monkeypatch):
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    monkeypatch.setenv("ADMIN_API_KEY", "testkey")
    db = importlib.import_module("agents.dashboard.main")
    client = TestClient(db.app)

    resp = client.get("/admin/get_publishing_config")
    assert resp.status_code == 401
