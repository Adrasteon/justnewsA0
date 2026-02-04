import asyncio

import pytest
from fastapi.testclient import TestClient

from agents.crawler import main as crawler_main


@pytest.mark.asyncio
async def test_stop_job_cancels_running_job(monkeypatch):
    # Replace the real background job with a test-friendly coroutine that waits
    async def fake_run(job_id, domains, max_articles, concurrent, profile_overrides):
        # Simulate a running job that can be cancelled
        try:
            crawler_main.crawl_jobs[job_id]["status"] = "running"
            await asyncio.sleep(1.0)
            # Simulate successful completion
            try:
                from agents.crawler.job_store import set_result

                set_result(job_id, {"articles": []})
            except Exception:
                crawler_main.crawl_jobs[job_id] = {
                    "status": "completed",
                    "result": {"articles": []},
                }
        except asyncio.CancelledError:
            # Mark as cancelled
            try:
                from agents.crawler.job_store import set_error

                set_error(job_id, "cancelled by test")
            except Exception:
                crawler_main.crawl_jobs[job_id] = {
                    "status": "failed",
                    "error": "cancelled",
                }
            raise

    monkeypatch.setattr(crawler_main, "run_crawl_background", fake_run)

    # Use base_url matching the allowed hosts to avoid the TrustedHostMiddleware rejecting testserver
    with TestClient(crawler_main.app, base_url="http://localhost") as client:
        # Start a new crawl (this schedules the background task)
        resp = client.post(
            "/unified_production_crawl", json={"args": [["example.com"]], "kwargs": {}}
        )
        # Add debug output when the endpoint fails so CI logs reveal the reason
        if resp.status_code != 202:
            # Make the failure message informative in CI logs
            raise AssertionError(
                f"Expected 202 when scheduling crawl, got {resp.status_code}: {resp.text}"
            )
        job_id = resp.json()["job_id"]

        # Ensure the job is tracked
        jobs = client.get("/jobs").json()
        assert job_id in jobs

        # Request stop for the job
        stop_resp = client.post(f"/stop_job/{job_id}")
        assert stop_resp.status_code == 200
        assert stop_resp.json().get("status") == "cancelled"

        # Give the task a moment to settle
        await asyncio.sleep(0.1)

        # Check stored job status
        status_resp = client.get(f"/job_status/{job_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data.get("status") in {"failed", "cancelled", "completed"}
