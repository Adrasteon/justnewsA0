import os

import pytest
from fastapi import HTTPException

from agents.c4ai.server import _require_api_token


def test_no_token_env_allows():
    os.environ.pop("CRAWLER_API_TOKEN", None)
    assert _require_api_token(None, None) is None


def test_invalid_and_valid_tokens(monkeypatch):
    monkeypatch.setenv("CRAWLER_API_TOKEN", "secret_token")
    with pytest.raises(HTTPException) as excinfo:
        _require_api_token(None, None)
    assert excinfo.value.status_code == 401

    with pytest.raises(HTTPException) as excinfo:
        _require_api_token("Bearer wrong", None)
    assert excinfo.value.status_code == 403

    assert _require_api_token("Bearer secret_token", None) is None
    assert _require_api_token(None, "secret_token") is None
