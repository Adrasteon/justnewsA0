from fastapi.testclient import TestClient

from agents.dashboard.main import app


def test_dashboard_root_serves_public_website():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    content = response.text
    assert "JustNews" in content
    assert "/api/crawl/status" in content
