import asyncio
import json
import types
from datetime import datetime

import pytest
from fastapi import HTTPException

import agents.common.auth_api as auth_api


def test_logout_revokes_refresh(monkeypatch):
    called = {}
    monkeypatch.setattr(
        auth_api, "revoke_refresh_token", lambda t: called.update({"revoked_token": t})
    )

    current_user = {"user_id": 1, "username": "u"}
    res = asyncio.run(
        auth_api.logout_user({"refresh_token": "r123"}, current_user=current_user)
    )
    assert res["message"] == "Logged out successfully"
    assert called.get("revoked_token") == "r123"


def test_get_current_user_info_converts_types():
    now = datetime.now()
    user = {
        "user_id": 5,
        "email": "e@x",
        "username": "bob",
        "full_name": "Bob",
        "role": auth_api.UserRole.RESEARCHER.value
        if hasattr(auth_api.UserRole, "RESEARCHER")
        else "researcher",
        "status": auth_api.UserStatus.ACTIVE.value,
        "created_at": now,
        "last_login": None,
    }

    out = asyncio.run(auth_api.get_current_user_info(current_user=user))
    assert out.user_id == 5
    assert out.email == "e@x"


def test_list_users_admin_and_nonadmin(monkeypatch):
    # non-admin should raise when checking admin dependency
    with pytest.raises(auth_api.HTTPException):
        asyncio.run(auth_api.get_admin_user(current_user={"role": "researcher"}))

    # admin path returns mapped results
    fake_users = [
        {
            "user_id": 1,
            "email": "a@b",
            "username": "a",
            "full_name": "A",
            "role": "admin",
            "status": auth_api.UserStatus.ACTIVE.value,
            "created_at": datetime.now(),
            "last_login": None,
        }
    ]
    monkeypatch.setattr(auth_api, "get_all_users", lambda limit, offset: fake_users)

    res = asyncio.run(
        auth_api.list_users(limit=10, offset=0, current_user={"role": "admin"})
    )
    assert isinstance(res, list)
    assert res[0].user_id == 1


def test_activate_deactivate_user(monkeypatch):
    # activate: not found -> 404
    monkeypatch.setattr(auth_api, "activate_user", lambda uid: False)
    with pytest.raises(auth_api.HTTPException):
        asyncio.run(
            auth_api.activate_user_account(
                123, current_user={"role": "admin", "username": "adm"}
            )
        )

    # success
    monkeypatch.setattr(auth_api, "activate_user", lambda uid: True)
    out = asyncio.run(
        auth_api.activate_user_account(
            123, current_user={"role": "admin", "username": "adm"}
        )
    )
    assert out["message"] == "User account activated successfully"

    # deactivate: return False -> 404
    monkeypatch.setattr(auth_api, "deactivate_user", lambda uid: False)
    with pytest.raises(auth_api.HTTPException):
        asyncio.run(
            auth_api.deactivate_user_account(
                321, current_user={"role": "admin", "username": "adm"}
            )
        )

    # success and ensure revoke_all_user_sessions called
    called = {}
    monkeypatch.setattr(auth_api, "deactivate_user", lambda uid: True)
    monkeypatch.setattr(
        auth_api,
        "revoke_all_user_sessions",
        lambda uid: called.update({"revoked": uid}),
    )
    out = asyncio.run(
        auth_api.deactivate_user_account(
            321, current_user={"role": "admin", "username": "adm"}
        )
    )
    assert out["message"] == "User account deactivated successfully"
    assert called.get("revoked") == 321


def test_perform_data_export_and_status(tmp_path, monkeypatch):
    _ = tmp_path
    export_id = "ex123"

    # stub get_user_by_id
    monkeypatch.setattr(
        auth_api,
        "get_user_by_id",
        lambda uid: {
            "user_id": uid,
            "email": "x@x",
            "username": "u",
            "full_name": "F",
            "role": "researcher",
            "status": auth_api.UserStatus.ACTIVE.value,
            "created_at": datetime.now(),
            "last_login": None,
        },
    )

    # make the working dir tmp so default export path is isolated
    monkeypatch.chdir(tmp_path)
    exports_dir = tmp_path / "data_exports"
    exports_dir.mkdir(exist_ok=True)

    # call perform_data_export directly into data_exports
    asyncio.run(
        auth_api.perform_data_export(
            export_id=export_id,
            user_id=42,
            include_sensitive=False,
            export_format="json",
            export_dir=exports_dir,
        )
    )

    # check files written into exports_dir
    status_path = exports_dir / f"{export_id}.json"
    data_path = exports_dir / f"{export_id}_data.json"
    assert status_path.exists()
    assert data_path.exists()

    # now test get_data_export_status success path by creating status file and calling function
    # write a valid status file with user_id 42
    st = {"user_id": 42, "status": "completed"}
    status_path.write_text(json.dumps(st))

    res = asyncio.run(
        auth_api.get_data_export_status(export_id, current_user={"user_id": 42})
    )
    assert isinstance(res, dict)


def test_download_data_export(tmp_path, monkeypatch):
    _ = tmp_path
    export_id = "exdl"

    # prepare data and status
    # put files into ./data_exports under the tmp working dir
    monkeypatch.chdir(tmp_path)
    exports_dir = tmp_path / "data_exports"
    exports_dir.mkdir(exist_ok=True)
    (exports_dir / f"{export_id}_data.json").write_text(
        json.dumps({"user_id": 7, "data": {}})
    )
    (exports_dir / f"{export_id}.json").write_text(
        json.dumps({"user_id": 7, "status": "completed"})
    )

    # call download_data_export with matching user
    resp = asyncio.run(
        auth_api.download_data_export(export_id, current_user={"user_id": 7})
    )
    assert hasattr(resp, "filename")


def test_perform_data_deletion_and_status(tmp_path, monkeypatch):
    req_id = "del123"

    # stub get_user_by_id and ensure auth_models.update_user_anonymized is patched
    monkeypatch.setattr(
        auth_api, "get_user_by_id", lambda uid: {"user_id": uid, "email": "u@x"}
    )
    monkeypatch.setattr(
        "agents.common.auth_models.update_user_anonymized",
        lambda user_id, anonymized_email, anonymized_username: None,
        raising=False,
    )
    monkeypatch.setattr(auth_api, "cleanup_related_data", lambda uid: None)

    monkeypatch.chdir(tmp_path)
    asyncio.run(
        auth_api.perform_data_deletion(request_id=req_id, user_id=99, reason="test")
    )

    status_dir = tmp_path / "data_deletions"
    assert any(status_dir.glob(f"{req_id}*.json"))


def test_consent_grant_with_invalid_type(monkeypatch):
    # Make consent_manager throw ValueError on invalid type
    monkeypatch.setattr(
        auth_api,
        "consent_manager",
        type("C", (), {"grant_consent": lambda **k: 1, "policies": {}})(),
    )

    # invalid enum value should produce 400
    with pytest.raises(auth_api.HTTPException):
        asyncio.run(
            auth_api.grant_user_consent(
                auth_api.ConsentGrantRequest(consent_type="bad_type"),
                current_user={"user_id": 1},
            )
        )


def test_data_minimization_admin_status(monkeypatch):
    # stub verify_token to be admin
    monkeypatch.setattr(
        auth_api, "verify_token", lambda token: {"user_id": 1, "role": "admin"}
    )

    class DM:
        def get_compliance_status(self):
            return {"ok": True}

    monkeypatch.setattr(auth_api, "DataMinimizationManager", lambda: DM())

    res = asyncio.run(
        auth_api.get_data_minimization_status(
            credentials=type("C", (), {"credentials": "t"})()
        )
    )
    assert res["status"] == "success"


from agents.common import auth_api as api  # noqa: E402


def test_get_current_user_invalid_token(monkeypatch):
    # verify_token returns None -> should raise 401
    monkeypatch.setattr(api, "verify_token", lambda t: None)
    fake_creds = types.SimpleNamespace(credentials="tok")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.get_current_user(fake_creds))

    assert exc.value.status_code == 401


def test_get_current_user_user_not_found(monkeypatch):
    # verify_token returns payload with user_id but get_user_by_id returns None
    monkeypatch.setattr(
        api, "verify_token", lambda t: types.SimpleNamespace(user_id=999)
    )
    monkeypatch.setattr(api, "get_user_by_id", lambda uid: None)
    fake_creds = types.SimpleNamespace(credentials="tok")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.get_current_user(fake_creds))

    assert exc.value.status_code == 401


def test_get_current_user_inactive_user(monkeypatch):
    # Valid token but user status is pending -> 403
    payload = types.SimpleNamespace(user_id=1)
    monkeypatch.setattr(api, "verify_token", lambda t: payload)
    user = {"user_id": 1, "status": api.UserStatus.PENDING.value}
    monkeypatch.setattr(api, "get_user_by_id", lambda uid: user)
    fake_creds = types.SimpleNamespace(credentials="tok")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.get_current_user(fake_creds))

    assert exc.value.status_code == 403


def test_get_admin_user_requires_admin(monkeypatch):
    # current_user role not admin -> raise 403
    fake_user = {"user_id": 1, "role": api.UserRole.RESEARCHER.value}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.get_admin_user(current_user=fake_user))
    assert exc.value.status_code == 403

    # admin allowed
    admin = {"user_id": 2, "role": api.UserRole.ADMIN.value}
    got = asyncio.run(api.get_admin_user(current_user=admin))
    assert got == admin


def test_register_user_existing_username(monkeypatch):
    # Simulate username already exists
    monkeypatch.setattr(
        api,
        "get_user_by_username_or_email",
        lambda key: {"user_id": 1} if key == "exists" else None,
    )
    from agents.common.auth_models import UserCreate

    payload = UserCreate(
        username="exists", email="e@example.com", password="x" * 12, full_name="Exists"
    )

    # BackgroundTasks param not necessary here; pass dummy
    from fastapi import BackgroundTasks

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.register_user(payload, BackgroundTasks()))
    assert exc.value.status_code == 400


def test_register_user_success(monkeypatch):
    # No existing user; create_user returns ID
    monkeypatch.setattr(api, "get_user_by_username_or_email", lambda key: None)
    monkeypatch.setattr(api, "create_user", lambda data: 42)

    from agents.common.auth_models import UserCreate

    payload = UserCreate(
        username="new", email="n@example.com", password="y" * 12, full_name="New"
    )
    from fastapi import BackgroundTasks

    res = asyncio.run(api.register_user(payload, BackgroundTasks()))
    assert res.user_id == 42
    assert res.requires_activation is True


def test_login_user_wrong_password(monkeypatch):
    # User found but wrong password
    user = {
        "user_id": 1,
        "username": "bob",
        "email": "b@example.com",
        "full_name": "Bob",
        "role": api.UserRole.RESEARCHER.value,
        "status": api.UserStatus.ACTIVE.value,
        "hashed_password": "h",
        "salt": "s",
        "last_login": None,
        "locked_until": None,
    }

    monkeypatch.setattr(api, "get_user_by_username_or_email", lambda key: user)
    monkeypatch.setattr(api, "verify_password", lambda pw, hp, s: False)

    # track increment_login_attempts called
    called = {"inc": False}
    monkeypatch.setattr(
        api, "increment_login_attempts", lambda uid: called.update({"inc": True})
    )

    from agents.common.auth_models import UserLogin

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.login_user(UserLogin(username_or_email="bob", password="wrong"))
        )

    assert exc.value.status_code == 401
    assert called["inc"] is True


def test_login_user_success(monkeypatch):
    # Good user and password -> returns tokens
    user = {
        "user_id": 2,
        "username": "alice",
        "email": "a@example.com",
        "full_name": "Alice",
        "role": api.UserRole.RESEARCHER.value,
        "status": api.UserStatus.ACTIVE.value,
        "hashed_password": "h",
        "salt": "s",
        "last_login": None,
        "locked_until": None,
    }

    monkeypatch.setattr(api, "get_user_by_username_or_email", lambda key: user)
    monkeypatch.setattr(api, "verify_password", lambda pw, hp, s: True)

    # track reset and update calls
    monkeypatch.setattr(api, "reset_login_attempts", lambda uid: None)
    tracked = {"updated": False}
    monkeypatch.setattr(
        api, "update_user_login", lambda uid: tracked.update({"updated": True})
    )

    monkeypatch.setattr(api, "create_access_token", lambda data: "access123")
    monkeypatch.setattr(api, "create_refresh_token", lambda data: "refresh456")
    monkeypatch.setattr(api, "store_refresh_token", lambda uid, tok: True)

    from agents.common.auth_models import UserLogin

    resp = asyncio.run(
        api.login_user(UserLogin(username_or_email="alice", password="pw"))
    )
    assert resp.access_token == "access123"
    assert resp.refresh_token == "refresh456"
    assert tracked["updated"] is True


def test_refresh_access_token_missing_or_invalid(monkeypatch):
    # missing token
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.refresh_access_token({}))
    assert exc.value.status_code == 400

    # invalid token
    monkeypatch.setattr(api, "validate_refresh_token", lambda t: None)
    with pytest.raises(HTTPException) as exc2:
        asyncio.run(api.refresh_access_token({"refresh_token": "bad"}))

    assert exc2.value.status_code == 401


def test_confirm_password_reset_invalid_and_success(monkeypatch):
    # invalid token
    monkeypatch.setattr(api, "validate_password_reset_token", lambda t: None)
    from agents.common.auth_models import PasswordReset

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            api.confirm_password_reset(PasswordReset(token="x", new_password="x" * 12))
        )
    assert exc.value.status_code == 400

    # success path
    monkeypatch.setattr(api, "validate_password_reset_token", lambda t: 7)
    monkeypatch.setattr(api, "update_user_password", lambda uid, p: True)
    monkeypatch.setattr(api, "mark_password_reset_token_used", lambda t: None)
    monkeypatch.setattr(api, "revoke_all_user_sessions", lambda uid: None)

    res = asyncio.run(
        api.confirm_password_reset(PasswordReset(token="ok", new_password="z" * 12))
    )
    assert isinstance(res, dict) and "message" in res
