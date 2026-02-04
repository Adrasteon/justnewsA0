from fastapi.testclient import TestClient

from agents.crawler import job_store
from agents.crawler.main import app


def test_clear_jobs_endpoint(monkeypatch):
    # Use in-memory fallback by forcing DB unavailable
    monkeypatch.setenv("MARIADB_HOST", "invalid-host-for-tests")
    # Allow testserver host through TrustedHostMiddleware
    monkeypatch.setenv("ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")
    # Create a job in the job store directly
    job_store.create_job("epitestjob", status="pending")

    client = TestClient(app)
    # Without token env set, endpoint should allow access
    resp = client.post("/clear_jobs", headers={"Host": "localhost"})
    assert resp.status_code == 200
    assert "Cleared" in resp.json().get("message", "")

    # If token set, endpoint requires token
    monkeypatch.setenv("CRAWLER_API_TOKEN", "secret")
    resp = client.post("/clear_jobs", headers={"Host": "localhost"})
    assert resp.status_code == 401 or resp.status_code == 403
    # Provide token
    headers = {"Authorization": "Bearer secret"}
    resp = client.post("/clear_jobs", headers={"Host": "localhost", **headers})
    assert resp.status_code == 200
