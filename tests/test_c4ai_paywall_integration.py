from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


class DummyCrawler:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def arun(self, url, config=None):
        # return an object with attributes expected by server
        return self._response


class DummyPaywall:
    def __init__(self, should_skip=True):
        self.should_skip = should_skip
        self.is_paywall = True
        self.confidence = 0.95
        self.reasons = ["detected-pattern"]


@pytest.mark.asyncio
async def test_paywall_aggregator_threshold(monkeypatch, tmp_path):
    # Prepare environment for aggregator
    dbfile = str(tmp_path / "paywall.db")
    monkeypatch.setenv("CRAWL4AI_PAYWALL_AGG_DB", dbfile)
    monkeypatch.setenv("CRAWL4AI_PAYWALL_THRESHOLD", "2")
    monkeypatch.setenv("CRAWL4AI_PERSIST_PAYWALLS", "true")

    # Prepare a fake crawler response
    res = SimpleNamespace(
        url="https://example.com/article",
        title="Example",
        html="<html><body>paywalled content</body></html>",
        markdown="Some content",
        links=["https://example.com"],
        status_code=200,
        success=True,
    )

    # Build fake crawl4ai module (AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode)
    import sys
    import types

    crawl4ai_mod = types.ModuleType("crawl4ai")

    class FakeBrowserConfig:
        def __init__(self, **kwargs):
            self._kwargs = kwargs

    class FakeCrawlerRunConfig:
        def __init__(self, cache_mode=None):
            self.cache_mode = cache_mode

    class FakeCacheMode:
        BYPASS = "BYPASS"

    class FakeAsyncWebCrawler:
        def __init__(self, config=None):
            self._config = config

        async def __aenter__(self):
            return DummyCrawler(res)

        async def __aexit__(self, exc_type, exc, tb):
            return False

    crawl4ai_mod.AsyncWebCrawler = FakeAsyncWebCrawler
    crawl4ai_mod.BrowserConfig = FakeBrowserConfig
    crawl4ai_mod.CrawlerRunConfig = FakeCrawlerRunConfig
    crawl4ai_mod.CacheMode = FakeCacheMode

    monkeypatch.setitem(sys.modules, "crawl4ai", crawl4ai_mod)

    # Fake paywall detector module
    paywall_mod = types.ModuleType("agents.crawler.enhancements.paywall_detector")

    class FakePaywallDetector:
        async def analyze(self, url, html=None, text=None):
            return DummyPaywall(should_skip=True)

    paywall_mod.PaywallDetector = FakePaywallDetector
    monkeypatch.setitem(
        sys.modules, "agents.crawler.enhancements.paywall_detector", paywall_mod
    )

    # Fake crawler_utils module with record_paywall_detection, RobotsChecker, RateLimiter
    cu_mod = types.ModuleType("agents.crawler.crawler_utils")

    def fake_record_paywall_detection(
        source_id=None, domain=None, skip_count=0, threshold=0, paywall_type=None
    ):
        # placeholder; we'll monkeypatch a collector below
        return None

    class FakeRobotsChecker:
        def is_allowed(self, url):
            return True

    class FakeRateLimiter:
        def acquire(self, domain):
            return None

    cu_mod.record_paywall_detection = fake_record_paywall_detection
    cu_mod.RobotsChecker = FakeRobotsChecker
    cu_mod.RateLimiter = FakeRateLimiter
    monkeypatch.setitem(sys.modules, "agents.crawler.crawler_utils", cu_mod)

    # Now import server module
    import importlib

    sys.modules.pop("agents.c4ai.server", None)
    server_mod = importlib.import_module("agents.c4ai.server")

    # Track calls to record_paywall_detection via monkeypatching the crawler_utils module
    calls = []

    def fake_record_paywall_detection_collector(
        source_id, domain, skip_count, threshold, paywall_type
    ):
        calls.append(
            {
                "domain": domain,
                "skip_count": skip_count,
                "threshold": threshold,
                "type": paywall_type,
            }
        )

    cu_mod.record_paywall_detection = fake_record_paywall_detection_collector

    client = TestClient(server_mod.app)

    # First request -> should detect paywall and increment aggregator but not yet record
    r1 = client.post("/crawl", json={"urls": ["https://example.com/article"]})
    assert r1.status_code == 200
    j1 = r1.json()
    assert j1["results"][0]["skip_ingest"] is True
    # No record yet
    assert len(calls) == 0

    # Second request -> should trigger threshold=2 and cause record_paywall_detection to be called
    r2 = client.post("/crawl", json={"urls": ["https://example.com/article"]})
    assert r2.status_code == 200
    j2 = r2.json()
    assert j2["results"][0]["skip_ingest"] is True

    import sqlite3

    with sqlite3.connect(dbfile) as conn:
        cur = conn.execute(
            "SELECT count FROM paywall_counts WHERE domain = ?", ("example.com",)
        )
        row = cur.fetchone()

    assert row is not None
    assert row[0] >= 2

    # Now aggregator should have caused a single record call
    assert len(calls) == 1
    assert calls[0]["domain"] == "example.com"
