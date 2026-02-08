import importlib

from fastapi.testclient import TestClient


def test_public_articles(monkeypatch):
    # Make the public API available
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    db = importlib.import_module("agents.dashboard.search_api")

    # Fake search service
    class FakeArticle:
        def __init__(self, id, title, content, source_name, published_date):
            self.id = id
            self.title = title
            self.content = content
            self.source_name = source_name
            self.published_date = published_date

    fake_articles = [
        FakeArticle(1, "Title 1", "A" * 400, "Test Source", "2025-11-20"),
        FakeArticle(2, "Title 2", "Short body", "Another", "2025-11-19"),
    ]

    class FakeSearchService:
        def get_recent_articles_with_search(self, n_results=10):
            return fake_articles[:n_results]

    monkeypatch.setattr(
        "agents.dashboard.search_api.get_search_service", lambda: FakeSearchService()
    )

    # Register router
    from fastapi import FastAPI

    app = FastAPI()
    db.include_public_api(app)
    client = TestClient(app)

    resp = client.get("/api/public/search/articles?n=2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_results"] == 2
    assert data["articles"][0]["id"] == 1
    assert "summary" in data["articles"][0]
    assert "source" in data["articles"][0]


def test_public_articles_main_compat(monkeypatch):
    # Ensure the main dashboard exposes /api/public/articles for the website
    monkeypatch.setenv("ADMIN_API_KEY", "testkey")
    monkeypatch.setenv("JUSTNEWS_ENABLE_PUBLIC_API", "1")
    import importlib

    db = importlib.import_module("agents.dashboard.main")

    # Fake search service
    class FakeArticle:
        def __init__(self, id, title, content, source_name, published_date):
            self.id = id
            self.title = title
            self.content = content
            self.source_name = source_name
            self.published_date = published_date

    fake_articles = [
        FakeArticle(1, "Title 1", "A" * 400, "Test Source", "2025-11-20"),
    ]

    class FakeSearchService:
        def get_recent_articles_with_search(self, n_results=10):
            return fake_articles[:n_results]

    monkeypatch.setattr(
        "common.semantic_search_service.get_search_service", lambda: FakeSearchService()
    )

    client = TestClient(db.app)
    resp = client.get("/api/public/articles?n=1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_results"] == 1
