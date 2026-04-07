import pytest

from agents.fact_checker import shim


@pytest.mark.asyncio
async def test_proxy_tool_fact_check_normalizes_response(monkeypatch):
    async def fake_post(endpoint: str, body: dict):
        assert endpoint.endswith("/fact_check")
        assert body["fact"] == "The claim"
        return {
            "verdict": "plausible",
            "confidence": 0.64,
            "explanation": "legacy verdict alias",
        }

    monkeypatch.setattr(shim, "_post_with_resilience", fake_post)

    result = await shim.proxy_tool("fact_check", {"fact": "The claim"})
    assert result["verdict"] == "Likely True"
    assert result["confidence"] == 0.64


@pytest.mark.asyncio
async def test_proxy_tool_verify_claim_payload_contract(monkeypatch):
    async def fake_post(endpoint: str, body: dict):
        assert endpoint.endswith("/fact_check")
        assert body == {
            "fact": "Claim A",
            "context": "ctx",
            "sources": ["s1"],
            "options": {},
        }
        return {"verdict": "Uncertain", "confidence": 0.5}

    monkeypatch.setattr(shim, "_post_with_resilience", fake_post)

    result = await shim.proxy_tool(
        "verify_claim",
        {"kwargs": {"claim": "Claim A", "context": "ctx", "sources": ["s1"]}},
    )
    assert result["verdict"] == "Uncertain"
    assert result["confidence"] == 0.5
