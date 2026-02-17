from agents.common.publisher_integration import publish_normalized_article


class _FakeArticle:
    def __init__(self):
        self.article_id = "a1"
        self.title = "Title"
        self.text = "Content"


def test_publish_http_success(monkeypatch, tmp_path):
    sent = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"result": "ok"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent["url"] = url
        sent["json"] = json
        sent["headers"] = headers
        return FakeResp()

    monkeypatch.setenv("PUBLISHER_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("PUBLISHER_API_KEY", "secret")
    monkeypatch.setattr("agents.common.publisher_integration.requests.post", fake_post)

    ok = publish_normalized_article(_FakeArticle(), author="CI")
    assert ok is True
    assert sent["url"].endswith("/api/publish/")
    assert sent["headers"]["X-API-KEY"] == "secret"


def test_publish_http_failure(monkeypatch):
    class FakeResp:
        status_code = 500

        def json(self):
            return {"result": "error"}

    def fake_post(url, json=None, headers=None, timeout=None):
        return FakeResp()

    monkeypatch.setenv("PUBLISHER_URL", "http://127.0.0.1:9000")
    monkeypatch.delenv("PUBLISHER_API_KEY", raising=False)
    monkeypatch.setattr("agents.common.publisher_integration.requests.post", fake_post)

    ok = publish_normalized_article(_FakeArticle(), author="CI")
    assert ok is False
