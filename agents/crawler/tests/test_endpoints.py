from pathlib import Path

from fastapi.testclient import TestClient

from agents.crawler import job_store
from agents.crawler import main as crawler_main
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


def test_update_triage_adapter_endpoint_persists_examples(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        crawler_main,
        "TRIAGE_TRAINING_DATA_PATH",
        tmp_path / "triage_training.jsonl",
    )

    client = TestClient(app)
    payload = {
        "args": [],
        "kwargs": {
            "examples": [
                {
                    "task_type": "ingestion_triage",
                    "input_text": "URL: https://example.com/news\nTitle: Story",
                    "expected_output": {"decision": "accept"},
                    "importance_score": 0.9,
                }
            ]
        },
    }

    resp = client.post("/update_triage_adapter", json=payload, headers={"Host": "localhost"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "success"
    assert body.get("accepted") == 1

    out_file = tmp_path / "triage_training.jsonl"
    assert out_file.exists()
    lines = out_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
