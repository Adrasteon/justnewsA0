import os

import pytest
from fastapi import HTTPException

from agents.crawler.main import require_api_token


def test_no_token_env_allows():
    # Ensure unset env means open access
    os.environ.pop("CRAWLER_API_TOKEN", None)
    assert require_api_token(None, None) is None


def test_invalid_and_valid_tokens(monkeypatch):
    monkeypatch.setenv("CRAWLER_API_TOKEN", "secret_token")
    # Missing token
    with pytest.raises(HTTPException) as excinfo:
        require_api_token(None, None)
    assert excinfo.value.status_code == 401

    # Wrong token
    with pytest.raises(HTTPException) as excinfo:
        require_api_token("Bearer wrong", None)
    assert excinfo.value.status_code == 403

    # Correct via Authorization bearer
    assert require_api_token("Bearer secret_token", None) is None

    # Correct via X-Api-Token header
    assert require_api_token(None, "secret_token") is None
