from agents.dashboard.dashboard_engine import DashboardEngine


def test_get_crawl_scheduler_snapshot_includes_db_sources(monkeypatch):
    engine = DashboardEngine()

    sample_sources = [
        {"id": 1, "domain": "example.com", "name": "Example"},
        {"id": 2, "domain": "foo.com", "name": "Foo"},
    ]

    monkeypatch.setattr(
        "agents.crawler.crawler_utils.get_active_sources",
        lambda limit, include_paywalled=False: sample_sources,
    )

    snapshot = engine.get_crawl_scheduler_snapshot(include_runs=False)

    assert isinstance(snapshot, dict)
    assert "sources" in snapshot
    assert snapshot["sources"] == sample_sources
