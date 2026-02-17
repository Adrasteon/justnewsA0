import importlib
import sys

import pytest


def _import_crawler_module():
    module_name = "agents.crawler.crawler_engine"
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    return module


def test_build_hitl_candidate_payload_basic_fields():
    mod = _import_crawler_module()
    engine = mod.CrawlerEngine()

    article = {
        "url": "https://example.test/article/1",
        "content": "This is a short article body with a few words.",
        "extraction_metadata": {"link_density": 0.123},
        "confidence": 0.45,
        "language": "en",
        "source_id": "site-123",
        "title": "Test Article",
        "raw_html_ref": "s3://raw/1.html",
        "timestamp": "2025-11-13T12:00:00Z",
        "crawler_job_id": "job-xyz",
    }

    payload = engine._build_hitl_candidate_payload(article, None)
    assert payload is not None
    assert payload["url"] == article["url"]
    assert payload["site_id"] == "site-123"
    assert payload["extracted_title"] == "Test Article"
    assert "features" in payload
    features = payload["features"]
    assert isinstance(features.get("word_count"), int)
    assert features.get("link_density") == pytest.approx(0.123)
    assert features.get("confidence") == pytest.approx(0.45)
    assert features.get("language") == "en"


@pytest.mark.asyncio
async def test_submit_hitl_candidates_posts_without_network(tmp_path, monkeypatch):
    mod = _import_crawler_module()
    engine = mod.CrawlerEngine()

    # Ensure we attempt HITL but skip stats fetch to avoid network
    engine.hitl_enabled = True
    engine.hitl_base_url = "http://fake-hitl"
    engine.hitl_stats_interval = 0

    captured = {}

    def fake_post(url, json=None, timeout=None):  # noqa: ANN001
        # Capture the call and return a fake response with no-op raise_for_status
        captured["url"] = url
        captured["json"] = json

        class FakeResp:
            def raise_for_status(self_inner):
                return None

        return FakeResp()

    monkeypatch.setattr(mod.requests, "post", fake_post)

    article = {
        "url": "https://example.test/article/2",
        "content": "Words words words",
        "extraction_metadata": {"link_density": 0.5},
        "source_id": "site-abc",
        "title": "Another Article",
    }

    await engine._submit_hitl_candidates([article], None)

    assert "url" in captured
    assert captured["url"].endswith("/api/candidates")
    posted = captured["json"]
    assert posted["url"] == article["url"]
    assert posted["site_id"] == "site-abc"
    assert posted["extracted_title"] == "Another Article"
