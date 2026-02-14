import pytest

from agents.fact_checker import shim


def test_normalize_verdict_maps_legacy_and_unknown():
    assert shim._normalize_verdict("True") == "True"
    assert shim._normalize_verdict("likely false") == "Likely False"
    assert shim._normalize_verdict("proven") == "True"
    assert shim._normalize_verdict("bogus") == "Uncertain"


def test_status_from_verdict():
    assert shim._status_from_verdict("True") == "passed"
    assert shim._status_from_verdict("Likely True") == "passed"
    assert shim._status_from_verdict("Likely False") == "failed"
    assert shim._status_from_verdict("False") == "failed"
    assert shim._status_from_verdict("Uncertain") == "needs_review"


def test_build_payload_verify_claim_from_kwargs():
    payload = {"kwargs": {"claim": "Claim A", "context": "ctx", "sources": ["s1"]}}
    out = shim._build_fact_check_payload("verify_claim", payload)
    assert out == {
        "fact": "Claim A",
        "context": "ctx",
        "sources": ["s1"],
        "options": {},
    }


@pytest.mark.asyncio
async def test_proxy_verify_article_real_flow(monkeypatch):
    persisted = {}

    def fake_load(article_id: int):
        assert article_id == 42
        return {
            "id": 42,
            "title": "Title",
            "summary": "Summary text",
            "content": "Body",
            "url": "https://example.com/a",
            "source_id": 7,
        }

    async def fake_post(endpoint: str, body: dict):
        assert endpoint.endswith("/fact_check")
        assert body["fact"] == "Summary text"
        return {
            "verdict": "Likely True",
            "confidence": 0.88,
            "explanation": "Supported by credible sources",
            "trusted_sources": ["https://reuters.com/x"],
            "misleading_sources": [],
        }

    def fake_persist(article_id: int, fact_check_status: str, factual_accuracy_score: float, fact_check_details: dict):
        persisted["article_id"] = article_id
        persisted["fact_check_status"] = fact_check_status
        persisted["score"] = factual_accuracy_score
        persisted["details"] = fact_check_details

    monkeypatch.setattr(shim, "_load_article_for_fact_check", fake_load)
    monkeypatch.setattr(shim, "_post_with_resilience", fake_post)
    monkeypatch.setattr(shim, "_persist_article_fact_check", fake_persist)

    result = await shim.proxy_tool("verify_article", {"article_id": 42})

    assert result["status"] == "success"
    assert result["article_id"] == 42
    assert result["fact_check_status"] == "passed"
    assert persisted["article_id"] == 42
    assert persisted["fact_check_status"] == "passed"
    assert persisted["score"] == 0.75


@pytest.mark.asyncio
async def test_proxy_tool_normalizes_forwarded_verdict(monkeypatch):
    async def fake_post(endpoint: str, body: dict):
        return {"verdict": "plausible", "confidence": 0.6, "explanation": "legacy verdict"}

    monkeypatch.setattr(shim, "_post_with_resilience", fake_post)

    result = await shim.proxy_tool("fact_check", {"fact": "A claim"})
    assert result["verdict"] == "Likely True"
    assert result["confidence"] == 0.6
