"""Unit tests for the synthesizer transparency gate."""

from typing import Any

import pytest

from agents.synthesizer.main import check_transparency_gateway


class _StubResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


def test_transparency_gateway_success(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"integrity": {"status": "ok"}, "counts": {"facts": 1}}

    def _mock_get(url: str, timeout: float):  # pylint: disable=unused-argument
        return _StubResponse(payload)

    monkeypatch.setattr("agents.synthesizer.main.requests.get", _mock_get)
    assert check_transparency_gateway(
        base_url="http://localhost:8013/transparency", timeout=1.0, required=True
    )


def test_transparency_gateway_failure_required(monkeypatch: pytest.MonkeyPatch) -> None:
    def _mock_get(url: str, timeout: float):  # pylint: disable=unused-argument
        raise RuntimeError("boom")

    monkeypatch.setattr("agents.synthesizer.main.requests.get", _mock_get)

    with pytest.raises(RuntimeError):
        check_transparency_gateway(
            base_url="http://localhost", timeout=1.0, required=True
        )


def test_transparency_gateway_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    def _mock_get(url: str, timeout: float):  # pylint: disable=unused-argument
        raise RuntimeError("boom")

    monkeypatch.setattr("agents.synthesizer.main.requests.get", _mock_get)

    assert not check_transparency_gateway(
        base_url="http://localhost", timeout=1.0, required=False
    )
