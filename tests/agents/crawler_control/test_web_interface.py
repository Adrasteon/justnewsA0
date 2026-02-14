import requests
from fastapi.testclient import TestClient

from agents.crawler_control import main as crawler_main


def test_root_serves_html(tmp_path, monkeypatch):
    client = TestClient(crawler_main.app)
    response = client.get("/")
    assert response.status_code == 200
    assert "JustNews Crawler Dashboard" in response.text


class DummyResp:
    def __init__(self, json_obj):
        self._json = json_obj

    def json(self):
        return self._json

    def raise_for_status(self):
        return None


def test_api_start_crawl(monkeypatch):
    client = TestClient(crawler_main.app)

    # Patch requests.post used to talk to the crawler agent
    dummy = DummyResp({"job": {"id": "1234", "status": "started"}})

    def fake_post(url, json=None, **kwargs):
        return dummy

    monkeypatch.setattr(requests, "post", fake_post)

    payload = {
        "domains": "example.com",
        "max_sites": 1,
        "max_articles_per_site": 2,
        "concurrent_sites": 1,
        "strategy": "auto",
        "enable_ai": False,
        "timeout": 60,
        "user_agent": "test-agent",
    }
    response = client.post("/api/crawl/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "job" in data
    assert data["job"]["status"] == "started"


def test_app_startup_db_warmup(monkeypatch):
    # Ensure DB warmup step on startup is not fatal and runs when available
    import agents.crawler_control.main as crawler_main

    called = {"closed": False}

    def fake_create_database_service():
        class DB:
            def close(self):
                called["closed"] = True

        return DB()

    monkeypatch.setattr(
        crawler_main, "create_database_service", fake_create_database_service
    )
    with TestClient(crawler_main.app) as client:
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json().get("ready") in (True, False)
    # Ensure warmup close was called
    assert called["closed"] is True


def test_api_start_crawl_builds_profile_overrides_from_crawl4ai(monkeypatch):
    client = TestClient(crawler_main.app)

    captured = {}

    class DummyAcceptedResp:
        def json(self):
            return {"status": "accepted", "job_id": "job-1"}

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return DummyAcceptedResp()

    monkeypatch.setattr(requests, "post", fake_post)

    payload = {
        "domains": "example.com",
        "max_articles_per_site": 4,
        "crawl4ai": {
            "crawl_depth": 2,
            "max_pages": 12,
            "follow_internal_links": True,
            "follow_external": False,
            "run_config": {"word_count_threshold": 120},
        },
    }

    response = client.post("/api/crawl/start", json=payload)
    assert response.status_code == 200
    forwarded = captured["json"]
    assert forwarded["kwargs"]["profile_overrides"]["example.com"]["extra"]["crawl_depth"] == 2
    assert forwarded["kwargs"]["profile_overrides"]["example.com"]["max_pages"] == 12
    assert forwarded["kwargs"]["profile_overrides"]["example.com"]["run_config"]["word_count_threshold"] == 120


def test_start_crawl_tool_accepts_domains_in_kwargs(monkeypatch):
    client = TestClient(crawler_main.app)

    captured = {}

    class DummyAcceptedResp:
        def json(self):
            return {"status": "accepted", "job_id": "job-2"}

        def raise_for_status(self):
            return None

    def fake_post(url, json=None, **kwargs):
        captured["json"] = json
        return DummyAcceptedResp()

    monkeypatch.setattr(requests, "post", fake_post)

    tool_payload = {
        "args": [],
        "kwargs": {
            "domains": "example.org",
            "crawl4ai": {
                "crawl_depth": 1,
                "run_config": {"score_links": True},
            },
        },
    }
    response = client.post("/start_crawl", json=tool_payload)
    assert response.status_code == 200
    profile = captured["json"]["kwargs"]["profile_overrides"]["example.org"]
    assert profile["extra"]["crawl_depth"] == 1
    assert profile["run_config"]["score_links"] is True


def test_api_crawl_options_endpoint():
    client = TestClient(crawler_main.app)
    response = client.get("/api/crawl/options")
    assert response.status_code == 200
    data = response.json()
    assert "crawl4ai" in data
    assert "crawl_depth" in data["crawl4ai"]["top_level"]
