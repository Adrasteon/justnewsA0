import asyncio
from types import SimpleNamespace

import pytest
from fastapi.security import HTTPAuthorizationCredentials

import agents.common.auth_api as auth_api


def test_get_current_user_success(monkeypatch):
    # Patch token verification and user lookup
    monkeypatch.setattr(
        auth_api, "verify_token", lambda token: SimpleNamespace(user_id=1)
    )
    monkeypatch.setattr(
        auth_api,
        "get_user_by_id",
        lambda uid: {
            "user_id": 1,
            "status": auth_api.UserStatus.ACTIVE.value,
            "username": "u",
            "email": "e",
            "full_name": "f",
            "created_at": None,
            "last_login": None,
        },
    )

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
    user = asyncio.run(auth_api.get_current_user(creds))
    assert user["user_id"] == 1


def test_get_current_user_invalid_token(monkeypatch):
    monkeypatch.setattr(auth_api, "verify_token", lambda token: None)

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad")
    with pytest.raises(auth_api.HTTPException) as exc:
        asyncio.run(auth_api.get_current_user(creds))

    assert exc.value.status_code == auth_api.status.HTTP_401_UNAUTHORIZED


def test_get_admin_user_denied():
    # Non-admin user should receive 403
    user = {"role": "user"}
    with pytest.raises(auth_api.HTTPException) as exc:
        asyncio.run(auth_api.get_admin_user(user))
    assert exc.value.status_code == auth_api.status.HTTP_403_FORBIDDEN


def test_register_user_conflict(monkeypatch):
    # Simulate existing username
    monkeypatch.setattr(
        auth_api, "get_user_by_username_or_email", lambda x: {"user_id": 1}
    )

    from agents.common.auth_models import UserCreate

    user_data = UserCreate(
        username="u1", email="e1@example.com", password="a" * 12, full_name="Full Name"
    )

    with pytest.raises(auth_api.HTTPException) as exc:
        asyncio.run(auth_api.register_user(user_data, background_tasks=None))

    assert exc.value.status_code == auth_api.status.HTTP_400_BAD_REQUEST


def test_login_user_success_sync(monkeypatch):
    # Prepare fake user and monkeypatch dependencies
    fake_user = {
        "user_id": 10,
        "username": "bob",
        "email": "bob@example.com",
        "hashed_password": "h",
        "salt": "s",
        "status": auth_api.UserStatus.ACTIVE.value,
        "full_name": "Bob",
        "last_login": None,
        "role": auth_api.UserRole.RESEARCHER.value if hasattr(auth_api, "UserRole") else "researcher",
    }

    monkeypatch.setattr(auth_api, "get_user_by_username_or_email", lambda u: fake_user)
    monkeypatch.setattr(auth_api, "verify_password", lambda pw, h, s: True)
    monkeypatch.setattr(auth_api, "reset_login_attempts", lambda uid: None)
    monkeypatch.setattr(auth_api, "update_user_login", lambda uid: None)
    monkeypatch.setattr(auth_api, "create_access_token", lambda data: "ATOKEN")
    monkeypatch.setattr(auth_api, "create_refresh_token", lambda data: "RTOKEN")
    monkeypatch.setattr(auth_api, "store_refresh_token", lambda uid, token: True)

    from agents.common.auth_models import UserLogin

    login = UserLogin(username_or_email="bob", password="secret")
    res = asyncio.run(auth_api.login_user(login))

    assert res.access_token == "ATOKEN"
    assert res.refresh_token == "RTOKEN"


from datetime import UTC, datetime, timedelta  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from agents.common.auth_models import UserCreate, UserLogin, UserStatus  # noqa: E402


@pytest.mark.asyncio
async def test_register_user_existing_username(monkeypatch):
    # Simulate username already exists
    monkeypatch.setattr(
        auth_api, "get_user_by_username_or_email", lambda x: {"username": x}
    )

    with pytest.raises(HTTPException) as ei:
        await auth_api.register_user(
            UserCreate(
                email="a@b.com",
                username="bob",
                full_name="Bob",
                password="pw",
                role="researcher",
            ),
            None,
        )
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_register_user_success(monkeypatch):
    # No existing user -> create_user returns new id
    monkeypatch.setattr(auth_api, "get_user_by_username_or_email", lambda x: None)
    monkeypatch.setattr(auth_api, "create_user", lambda data: 123)

    from fastapi import BackgroundTasks

    resp = await auth_api.register_user(
        UserCreate(
            email="c@d.com",
            username="carol",
            full_name="Carol",
            password="pw",
            role="researcher",
        ),
        BackgroundTasks(),
    )
    assert resp.user_id == 123
    assert resp.requires_activation is True


@pytest.mark.asyncio
async def test_login_user_invalid_user(monkeypatch):
    monkeypatch.setattr(auth_api, "get_user_by_username_or_email", lambda x: None)
    with pytest.raises(HTTPException) as ei:
        await auth_api.login_user(UserLogin(username_or_email="x", password="p"))
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_login_user_locked(monkeypatch):
    future = datetime.now(UTC) + timedelta(minutes=5)
    user = {
        "user_id": 1,
        "username": "bob",
        "email": "bob@ex",
        "salt": "s",
        "hashed_password": "h",
        "status": UserStatus.ACTIVE.value,
        "locked_until": future,
    }
    monkeypatch.setattr(auth_api, "get_user_by_username_or_email", lambda x: user)
    with pytest.raises(HTTPException) as ei:
        await auth_api.login_user(UserLogin(username_or_email="bob", password="p"))
    assert ei.value.status_code == 423


@pytest.mark.asyncio
async def test_login_user_success(monkeypatch):
    now = datetime.now(UTC)
    user = {
        "user_id": 2,
        "username": "alice",
        "email": "alice@ex",
        "full_name": "Alice",
        "role": "researcher",
        "salt": "s",
        "hashed_password": "h",
        "status": UserStatus.ACTIVE.value,
        "last_login": now,
    }

    monkeypatch.setattr(auth_api, "get_user_by_username_or_email", lambda x: user)
    monkeypatch.setattr(auth_api, "verify_password", lambda pw, h, s: True)
    monkeypatch.setattr(auth_api, "reset_login_attempts", lambda uid: None)
    monkeypatch.setattr(auth_api, "update_user_login", lambda uid: None)
    monkeypatch.setattr(auth_api, "create_access_token", lambda data: "access.abc")
    monkeypatch.setattr(auth_api, "create_refresh_token", lambda data: "refresh.xyz")
    monkeypatch.setattr(auth_api, "store_refresh_token", lambda uid, tok: True)

    out = await auth_api.login_user(UserLogin(username_or_email="alice", password="pw"))
    assert out.access_token == "access.abc"
    assert out.refresh_token == "refresh.xyz"


@pytest.mark.asyncio
async def test_refresh_token_missing(monkeypatch):
    with pytest.raises(HTTPException) as ei:
        await auth_api.refresh_access_token({})
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_refresh_token_invalid(monkeypatch):
    monkeypatch.setattr(auth_api, "validate_refresh_token", lambda t: None)
    with pytest.raises(HTTPException) as ei:
        await auth_api.refresh_access_token({"refresh_token": "nope"})
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_success(monkeypatch):
    monkeypatch.setattr(auth_api, "validate_refresh_token", lambda t: 77)
    monkeypatch.setattr(
        auth_api,
        "get_user_by_id",
        lambda uid: {
            "user_id": 77,
            "username": "u",
            "email": "u@e",
            "role": "researcher",
            "status": UserStatus.ACTIVE.value,
        },
    )
    monkeypatch.setattr(auth_api, "create_access_token", lambda data: "new.access")

    out = await auth_api.refresh_access_token({"refresh_token": "ok"})
    assert out["access_token"] == "new.access"


@pytest.mark.asyncio
async def test_password_reset_request_not_found(monkeypatch):
    monkeypatch.setattr(auth_api, "get_user_by_username_or_email", lambda x: None)
    resp = await auth_api.request_password_reset(type("R", (), {"email": "no@e"}), None)
    assert "If an account with this email exists" in resp.message


@pytest.mark.asyncio
async def test_password_reset_request_found(monkeypatch):
    monkeypatch.setattr(
        auth_api, "get_user_by_username_or_email", lambda x: {"user_id": 5}
    )
    called = {}

    def create_token(uid):
        called["created"] = uid

    monkeypatch.setattr(auth_api, "create_password_reset_token", create_token)
    resp = await auth_api.request_password_reset(
        type("R", (), {"email": "yes@e"}), None
    )
    assert "password reset" in resp.message
    assert called.get("created") == 5


@pytest.mark.asyncio
async def test_confirm_password_reset_invalid_token(monkeypatch):
    monkeypatch.setattr(auth_api, "validate_password_reset_token", lambda t: None)
    with pytest.raises(HTTPException) as ei:
        await auth_api.confirm_password_reset(
            type("P", (), {"token": "bad", "new_password": "x"})
        )
    assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_confirm_password_reset_success(monkeypatch):
    monkeypatch.setattr(auth_api, "validate_password_reset_token", lambda t: 9)
    monkeypatch.setattr(auth_api, "update_user_password", lambda uid, pw: True)
    flags = {}
    monkeypatch.setattr(
        auth_api,
        "mark_password_reset_token_used",
        lambda tok: flags.update({"used": tok}),
    )
    monkeypatch.setattr(
        auth_api, "revoke_all_user_sessions", lambda uid: flags.update({"revoked": uid})
    )

    out = await auth_api.confirm_password_reset(
        type("P", (), {"token": "t", "new_password": "p"})
    )
    assert out["message"] == "Password reset successfully"
    assert flags["used"] == "t"
    assert flags["revoked"] == 9
