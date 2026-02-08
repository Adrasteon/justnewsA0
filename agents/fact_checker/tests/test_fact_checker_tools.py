import asyncio

from agents.fact_checker.tools import (
    assess_credibility,
    extract_claims,
    validate_fact_check_result,
    validate_is_news_cpu,
    verify_claims_cpu,
)


def test_validate_is_news_cpu_basic():
    res = asyncio.run(validate_is_news_cpu("Breaking news: something happened."))
    assert isinstance(res, dict)
    assert "is_news" in res
    assert "confidence" in res
    assert "method" in res
    assert "analysis_timestamp" in res
    assert "processing_time" in res and res["processing_time"] >= 0


def test_verify_claims_cpu_basic():
    claims = ["The event happened in 2020"]
    sources = ["This article states the event happened in 2020"]
    res = asyncio.run(verify_claims_cpu(claims, sources))
    assert "results" in res
    assert "total_claims" in res
    assert "verified_claims" in res
    assert res["method"] == "cpu_fallback"
    assert "processing_time" in res and res["processing_time"] >= 0


def test_validate_fact_check_result():
    valid = validate_fact_check_result({"analysis_timestamp": "2025-01-01T00:00:00Z"})
    assert valid
    invalid = validate_fact_check_result("not a dict")
    assert not invalid


def test_extract_claims_and_assess_credibility(monkeypatch):
    # Monkeypatch underlying engine functions to return simple responses
    class FakeEngine:
        def extract_claims(self, content):
            return {"claims": ["claim1", "claim2"]}

        def assess_credibility(self, content, **kwargs):
            return {"credibility_score": 0.8, "reliability": "good"}

    monkeypatch.setattr(
        "agents.fact_checker.tools.get_fact_checker_engine", lambda: FakeEngine()
    )

    claims = extract_claims("Some article content")
    assert isinstance(claims, list)
    assert claims == ["claim1", "claim2"]

    cred = assess_credibility("Some article content")
    assert isinstance(cred, dict)
    assert "credibility_score" in cred


async def _sample_coro():
    return 42


def test__await_if_needed_in_async_context():
    from agents.fact_checker.tools import _await_if_needed

    async def runner():
        task = _await_if_needed(_sample_coro())
        # Task should be awaitable and produce the value
        result = await task
        assert result == 42

    asyncio.run(runner())
