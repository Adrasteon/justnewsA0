import pytest

from agents.fact_checker import shim


@pytest.mark.asyncio
async def test_verify_article_flow_uses_external_backend_contract(monkeypatch):
    persisted = {}

    def fake_load(article_id: int):
        assert article_id == 7
        return {
            "id": 7,
            "title": "Title",
            "summary": "Summary text",
            "content": "Body text",
            "url": "https://example.com/a",
            "source_id": 2,
        }

    async def fake_post(endpoint: str, body: dict):
        assert endpoint.endswith("/fact_check")
        assert body["fact"] == "Summary text"
        return {
            "verdict": "Likely True",
            "confidence": 0.88,
            "explanation": "Supported",
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

    result = await shim.proxy_tool("verify_article", {"article_id": 7})

    assert result["status"] == "success"
    assert result["article_id"] == 7
    assert result["fact_check_status"] == "passed"
    assert persisted["article_id"] == 7
    assert persisted["fact_check_status"] == "passed"
    assert persisted["score"] == 0.75
