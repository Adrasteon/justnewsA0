from agents.crawler import tools as crawler_tools


class FakeCrawlerEngine:
    def get_performance_report(self):
        return {"requests_per_minute": 120, "errors": 0}


def test_get_crawler_info_monkeypatch(monkeypatch):
    # Monkeypatch the CrawlerEngine class used in the module
    monkeypatch.setattr(crawler_tools, "CrawlerEngine", FakeCrawlerEngine)
    info = crawler_tools.get_crawler_info()
    assert info["crawler_type"] == "UnifiedProductionCrawler"
    assert "requests_per_minute" in info["performance_metrics"]


def test_reset_performance_metrics_noop(monkeypatch):
    # The function tries to import reset method; we ensure no exception is raised
    crawler_tools.reset_performance_metrics()
    assert True
