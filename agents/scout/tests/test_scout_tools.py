import pytest

from agents.scout.tools import (
    analyze_sentiment_tool,
    deep_crawl_tool,
    detect_bias_tool,
    discover_sources_tool,
)


class FakeResult:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class FakeEngine:
    def __init__(self):
        self._raise = False

    async def discover_sources(self, domains, max_sources):
        if self._raise:
            raise RuntimeError("discover error")
        return ["https://example.com"]

    async def deep_crawl_site(self, site_url, max_pages):
        if self._raise:
            raise RuntimeError("deep crawl error")
        return {"success": True, "pages_crawled": 2, "articles_found": ["a", "b"]}

    async def analyze_sentiment(self, text):
        if self._raise:
            raise RuntimeError("sentiment fail")
        return FakeResult(
            result="positive", confidence=0.87, model_used="mini", processing_time=0.01
        )

    async def detect_bias(self, text):
        if self._raise:
            raise RuntimeError("bias fail")
        return FakeResult(
            result={"bias_score": 0.2, "bias_type": "lean_left"},
            model_used="bias-model",
            processing_time=0.02,
        )


@pytest.mark.asyncio
async def test_discover_sources_success():
    engine = FakeEngine()
    res = await discover_sources_tool(engine, domains=["example.com"], max_sources=5)
    assert res["success"]
    assert res["total_found"] == 1
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_discover_sources_failure():
    engine = FakeEngine()
    engine._raise = True
    res = await discover_sources_tool(engine, domains=["example.com"], max_sources=5)
    assert not res["success"]
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_deep_crawl_success():
    engine = FakeEngine()
    res = await deep_crawl_tool(engine, site_url="https://example.com", max_pages=5)
    assert res["success"]
    assert res["pages_crawled"] == 2
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_deep_crawl_failure():
    engine = FakeEngine()
    engine._raise = True
    res = await deep_crawl_tool(engine, site_url="https://bad.example.com", max_pages=5)
    assert not res["success"]
    assert res["processing_time"] >= 0


@pytest.mark.asyncio
async def test_analyze_sentiment_success():
    engine = FakeEngine()
    text = "This is great!"
    res = await analyze_sentiment_tool(engine, text)
    assert res["success"]
    assert res["sentiment"] == "positive"
    assert res["confidence"] == pytest.approx(0.87, rel=1e-3)


@pytest.mark.asyncio
async def test_detect_bias_success():
    engine = FakeEngine()
    text = "This is biased"
    res = await detect_bias_tool(engine, text)
    assert res["success"]
    assert res["bias_score"] == pytest.approx(0.2, rel=1e-3)
    assert res["bias_type"] == "lean_left"
