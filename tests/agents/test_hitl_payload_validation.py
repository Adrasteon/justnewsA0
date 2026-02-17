def _patch_crawler_init(monkeypatch):
    # Patch heavy or environment-dependent functions used during CrawlerEngine.__init__
    monkeypatch.setattr(
        "agents.crawler.crawler_engine.initialize_connection_pool", lambda: None
    )
    monkeypatch.setattr(
        "agents.crawler.crawler_engine.create_crawling_performance_table", lambda: None
    )
    monkeypatch.setattr(
        "agents.crawler.crawler_engine.get_performance_monitor", lambda: None
    )
    monkeypatch.setattr(
        "agents.crawler.crawler_engine.start_performance_monitoring",
        lambda interval_seconds=60: None,
    )


def test_build_hitl_payload_validates_against_candidate_event(monkeypatch):
    """Ensure the payload produced by CrawlerEngine._build_hitl_candidate_payload
    is accepted by the HITL `CandidateEvent` Pydantic model.
    """
    _patch_crawler_init(monkeypatch)

    from agents.crawler.crawler_engine import CrawlerEngine
    from agents.hitl_service.app import CandidateEvent

    engine = CrawlerEngine()

    # Minimal realistic article example (mirrors fields produced by the crawler)
    article = {
        "url": "https://example.com",
        "title": "Example Domain",
        "content": "This domain is for use in documentation examples without needing permission. Avoid use in operations.\nLearn more",
        "raw_html_ref": "archive_storage/raw_html/example.html",
        "timestamp": "2025-11-13T16:15:10.772400+00:00",
        "confidence": 0.35,
        "paywall_flag": False,
        "language": "en",
        "extraction_metadata": {"word_count": 17, "link_density": None},
    }

    payload = engine._build_hitl_candidate_payload(article, None)
    assert isinstance(payload, dict)

    # Should validate without raising
    evt = CandidateEvent(**payload)
    assert evt.url == article["url"]
    assert evt.extracted_title == article["title"]
    assert evt.extracted_text is not None


def test_build_hitl_payload_missing_url_returns_none(monkeypatch):
    _patch_crawler_init(monkeypatch)
    from agents.crawler.crawler_engine import CrawlerEngine

    engine = CrawlerEngine()
    article = {"title": "No URL here"}
    payload = engine._build_hitl_candidate_payload(article, None)
    assert payload is None


def test_link_density_handling(monkeypatch):
    _patch_crawler_init(monkeypatch)
    from agents.crawler.crawler_engine import CrawlerEngine
    from agents.hitl_service.app import CandidateEvent

    engine = CrawlerEngine()

    # link_density as string should be ignored
    article_str = {
        "url": "https://example.com/str",
        "content": "one two three",
        "extraction_metadata": {"link_density": "0.2"},
    }
    p1 = engine._build_hitl_candidate_payload(article_str, None)
    evt1 = CandidateEvent(**p1)
    assert evt1.features is None or "link_density" not in (evt1.features or {})

    # link_density as float should be present
    article_float = {
        "url": "https://example.com/float",
        "content": "one two three",
        "extraction_metadata": {"link_density": 0.2},
    }
    p2 = engine._build_hitl_candidate_payload(article_float, None)
    evt2 = CandidateEvent(**p2)
    assert isinstance(evt2.features.get("link_density"), float)


def test_large_text_word_count_and_features_none(monkeypatch):
    _patch_crawler_init(monkeypatch)
    from agents.crawler.crawler_engine import CrawlerEngine
    from agents.hitl_service.app import CandidateEvent

    engine = CrawlerEngine()
    # Large content -> correct word count
    content = "word " * 1000
    article = {"url": "https://example.com/large", "content": content}
    payload = engine._build_hitl_candidate_payload(article, None)
    evt = CandidateEvent(**payload)
    assert evt.features and evt.features.get("word_count") == 1000


def test_site_id_from_site_config(monkeypatch):
    _patch_crawler_init(monkeypatch)
    from agents.crawler.crawler_engine import CrawlerEngine
    from agents.hitl_service.app import CandidateEvent

    engine = CrawlerEngine()

    class DummySiteConfig:
        def __init__(self, source_id):
            self.source_id = source_id

    site = DummySiteConfig(source_id="source_123")
    article = {"url": "https://example.com/siteid", "content": "a b c"}
    payload = engine._build_hitl_candidate_payload(article, site)
    evt = CandidateEvent(**payload)
    assert evt.site_id == "source_123"


def test_crawler_job_id_preserved_and_features_none_when_empty(monkeypatch):
    _patch_crawler_init(monkeypatch)
    from agents.crawler.crawler_engine import CrawlerEngine
    from agents.hitl_service.app import CandidateEvent

    engine = CrawlerEngine()
    article = {"url": "https://example.com/jobid", "crawler_job_id": "job-xyz"}
    payload = engine._build_hitl_candidate_payload(article, None)
    evt = CandidateEvent(**payload)
    assert evt.crawler_job_id == "job-xyz"
    # No content -> features should be None
    assert evt.features is None
