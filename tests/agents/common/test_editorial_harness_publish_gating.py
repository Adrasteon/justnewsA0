import os

from agents.common.publisher_integration import verify_publish_token


def test_verify_publish_token_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLISH_APPROVAL_TOKEN", "secret123")
    assert verify_publish_token("secret123") is True
    assert verify_publish_token("wrong") is False


def test_verify_publish_token_file(tmp_path):
    token_file = tmp_path / "publish.token"
    token_file.write_text("filetoken")
    os.environ["PUBLISH_APPROVAL_TOKEN_FILE"] = str(token_file)
    try:
        assert verify_publish_token("filetoken") is True
        assert verify_publish_token("wrong") is False
    finally:
        del os.environ["PUBLISH_APPROVAL_TOKEN_FILE"]


"""
Tests for publish approval gating
"""
