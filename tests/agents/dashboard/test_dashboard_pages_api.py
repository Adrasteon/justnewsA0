from fastapi.testclient import TestClient

from agents.dashboard.main import app


def test_dashboard_pages_api_returns_pages():
    client = TestClient(app)
    # Ensure that even with missing config, endpoint returns a fallback
    import agents.dashboard.main as dashboard_main

    old_config = getattr(dashboard_main, "config", None)
    dashboard_main.config = {}
    resp = client.get("/api/dashboard/pages")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] == "success"
    assert "pages" in data
    assert isinstance(data["pages"], list)
    # Ensure at least Home and GPU Dashboard are present as pages
    paths = [p.get("path") for p in data["pages"]]
    assert "/" in paths
    assert "/gpu/dashboard" in paths
    # Verify the Crawler Control page (external) is present
    assert "http://localhost:8016/" in paths
    # Also ensure the page title is present
    titles = [p.get("title") for p in data["pages"]]
    assert "Crawler Control" in titles
    # Restore config
    dashboard_main.config = old_config
