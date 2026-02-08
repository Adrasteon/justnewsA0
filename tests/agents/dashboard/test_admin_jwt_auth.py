import importlib

from fastapi.testclient import TestClient


def test_get_publishing_config_jwt_admin(monkeypatch):
    """When ADMIN_API_KEY is not set an admin JWT (role=admin) should be accepted."""
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    db = importlib.import_module("agents.dashboard.main")
    # patch verify_token to return a TokenData-like object
    from agents.common.auth_models import TokenData

    def fake_verify(token):
        return TokenData(user_id=1, username="admin", email="admin@local", role="admin")

    monkeypatch.setattr("agents.common.auth_models.verify_token", fake_verify)
    # patch get_user_by_id to return a user with admin role
    monkeypatch.setattr(
        "agents.common.auth_models.get_user_by_id",
        lambda uid: {
            "user_id": 1,
            "username": "admin",
            "role": "admin",
            "status": "active",
        },
    )

    client = TestClient(db.app)
    resp = client.get(
        "/admin/get_publishing_config", headers={"Authorization": "Bearer faketoken"}
    )
    assert resp.status_code == 200


def test_set_publishing_config_jwt_admin(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    db = importlib.import_module("agents.dashboard.main")
    from agents.common.auth_models import TokenData

    def fake_verify(token):
        return TokenData(user_id=1, username="admin", email="admin@local", role="admin")

    monkeypatch.setattr("agents.common.auth_models.verify_token", fake_verify)
    monkeypatch.setattr(
        "agents.common.auth_models.get_user_by_id",
        lambda uid: {
            "user_id": 1,
            "username": "admin",
            "role": "admin",
            "status": "active",
        },
    )

    client = TestClient(db.app)
    resp = client.post(
        "/admin/set_publishing_config",
        json={"require_draft_fact_check_pass_for_publish": True},
        headers={"Authorization": "Bearer faketoken"},
    )
    assert resp.status_code == 200
    assert resp.json().get("status") == "success"


def test_get_publishing_config_jwt_denied(monkeypatch):
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    db = importlib.import_module("agents.dashboard.main")
    monkeypatch.setattr("agents.common.auth_models.verify_token", lambda token: None)
    client = TestClient(db.app)
    resp = client.get(
        "/admin/get_publishing_config", headers={"Authorization": "Bearer faketoken"}
    )
    assert resp.status_code == 401


def test_reload_protected(monkeypatch):
    """Ensure that the reload endpoint in dashboard requires admin credentials."""
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    db = importlib.import_module("agents.dashboard.main")
    # patch verify_token to return admin
    from agents.common.auth_models import TokenData

    monkeypatch.setattr(
        "agents.common.auth_models.verify_token",
        lambda token: TokenData(
            user_id=1, username="admin", email="admin@local", role="admin"
        ),
    )
    monkeypatch.setattr(
        "agents.common.auth_models.get_user_by_id",
        lambda uid: {
            "user_id": 1,
            "username": "admin",
            "role": "admin",
            "status": "active",
        },
    )
    client = TestClient(db.app)
    resp = client.post(
        "/admin/reload",
        json={"all": True},
        headers={"Authorization": "Bearer faketoken"},
    )
    # The reload endpoint returns results or raises bad request for no handlers
    # We expect a 400 because no handlers registered in tests. This still proves auth passed.
    assert resp.status_code in (400, 200)
