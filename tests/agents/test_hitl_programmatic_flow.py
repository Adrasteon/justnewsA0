import importlib
import sqlite3

from fastapi.testclient import TestClient


def _make_noop_coro():
    async def _noop(*args, **kwargs):
        return None

    return _noop


def test_programmatic_label_flow(tmp_path, monkeypatch):
    # Use a temporary DB for isolation
    db_path = tmp_path / "hitl_test.db"
    monkeypatch.setenv("HITL_DB_PATH", str(db_path))

    # Reload the module so it picks up the env var
    import agents.hitl_service.app as hitl_mod

    importlib.reload(hitl_mod)

    # Prevent network/background tasks from running during startup
    monkeypatch.setattr(hitl_mod, "register_with_mcp_bus", _make_noop_coro())
    monkeypatch.setattr(hitl_mod, "monitor_qa_health", _make_noop_coro())

    # mcp_client may attempt network calls; replace methods used with safe no-ops
    class DummyMCP:
        def register_agent(self, *a, **k):
            return None

        def call_tool(self, *a, **k):
            return None

        def list_agents(self):
            return {}

    monkeypatch.setattr(hitl_mod, "mcp_client", DummyMCP())

    # Ensure DB created
    hitl_mod.ensure_db()

    client = TestClient(hitl_mod.app)

    with client:
        # Post a candidate (no id) as the crawler would
        cand_payload = {
            "url": "https://example.com/test-flow",
            "extracted_title": "Test Flow",
            "extracted_text": "some text here",
            "raw_html_ref": "archive_storage/raw_html/test.html",
            "features": {"word_count": 3},
            "crawler_ts": "2025-11-13T00:00:00Z",
            "crawler_job_id": "job-abc",
        }

        r = client.post("/api/candidates", json=cand_payload)
        assert r.status_code == 200
        data = r.json()
        assert "candidate_id" in data
        cid = data["candidate_id"]

        # Next should return the candidate
        nb = client.get("/api/next?batch=10").json()
        assert nb.get("count", 0) >= 1
        found = False
        for c in nb.get("candidates", []):
            if c["id"] == cid:
                found = True
        assert found, "Candidate not found in /api/next results"

        # Post a label
        label_payload = {
            "candidate_id": cid,
            "label": "valid_news",
            "cleaned_text": "automated test",
            "annotator_id": "pytest",
        }
        lr = client.post("/api/label", json=label_payload)
        assert lr.status_code == 200
        ldata = lr.json()
        assert "label_id" in ldata

    # After client context, inspect DB directly
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT id, url, status FROM hitl_candidates WHERE id=?", (cid,))
    cand_row = cur.fetchone()
    assert cand_row is not None
    assert cand_row[2] == "labeled"

    # Check label row
    label_id = ldata.get("label_id")
    cur.execute(
        "SELECT id, candidate_id, label, ingestion_status FROM hitl_labels WHERE id=?",
        (label_id,),
    )
    label_row = cur.fetchone()
    assert label_row is not None
    # ingestion_status may be 'skipped' in test env
    assert label_row[1] == cid
    conn.close()
