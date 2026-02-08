import importlib

import pytest
from fastapi.testclient import TestClient


def test_synthesize_job_and_status(monkeypatch):
    monkeypatch.setenv("REQUIRE_TRANSPARENCY_AUDIT", "0")

    # Patch engine to avoid heavy model load
    class FakeEngine:
        def __init__(self):
            pass

    monkeypatch.setattr(
        "agents.synthesizer.main.SynthesizerEngine", FakeEngine, raising=False
    )
    synth_main = importlib.import_module("agents.synthesizer.main")
    synth_main.synthesizer_engine = FakeEngine()
    synth_main.transparency_gate_passed = True

    async def fake_synth(engine, articles, max_clusters, context, cluster_id=None):
        return {"status": "success", "synthesis": "ok"}

    monkeypatch.setattr("agents.synthesizer.tools.synthesize_gpu_tool", fake_synth)
    monkeypatch.setattr("agents.synthesizer.main.synthesize_gpu_tool", fake_synth)

    client = TestClient(synth_main.app)
    body = {
        "articles": [{"content": "A short article"}],
        "max_clusters": 1,
        "context": "news",
    }
    resp = client.post("/api/v1/articles/synthesize", json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    job_id = data["job_id"]

    # Get job status repeatedly until completed (but in our test async task will be scheduled quickly)
    import time

    for _ in range(10):
        r2 = client.get(f"/api/v1/articles/synthesize/{job_id}")
        assert r2.status_code == 200
        job = r2.json()
        if job.get("status") == "completed":
            assert job.get("result", {}).get("status") == "success"
            return
        time.sleep(0.1)
    pytest.fail("job did not complete in time")
