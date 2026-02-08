import csv
import importlib
import sqlite3
import sys
import uuid
from io import StringIO

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def hitl_client(tmp_path, monkeypatch):
    db_path = tmp_path / "hitl_service.db"
    monkeypatch.setenv("HITL_DB_PATH", str(db_path))
    # Ensure forwarding is disabled for isolated tests
    for var in (
        "HITL_FORWARD_AGENT",
        "HITL_FORWARD_TOOL",
        "HITL_CANDIDATE_FORWARD_AGENT",
        "HITL_CANDIDATE_FORWARD_TOOL",
        "HITL_TRAINING_FORWARD_AGENT",
        "HITL_TRAINING_FORWARD_TOOL",
    ):
        monkeypatch.delenv(var, raising=False)

    module_name = "agents.hitl_service.app"
    sys.modules.pop(module_name, None)
    hitl_module = importlib.import_module(module_name)

    async def _noop_async(*_args, **_kwargs):  # noqa: ANN002
        return None

    monkeypatch.setattr(hitl_module, "register_with_mcp_bus", _noop_async)
    monkeypatch.setattr(hitl_module, "monitor_qa_health", _noop_async)

    client = TestClient(hitl_module.app)
    with client:
        yield client, hitl_module


def _create_candidate_and_label(hitl_module, url, annotator_id="annotator"):
    candidate_id = str(uuid.uuid4())
    event = hitl_module.CandidateEvent(
        id=candidate_id,
        url=url,
        site_id="test-site",
        extracted_text="body",
    )
    hitl_module.insert_candidate(event)
    label_req = hitl_module.LabelRequest(
        candidate_id=candidate_id,
        label="valid_news",
        cleaned_text="clean text",
        annotator_id=annotator_id,
    )
    result = hitl_module.store_label(label_req)
    return candidate_id, result


def test_qa_endpoints_expose_pending_history_and_export(hitl_client, monkeypatch):
    client, hitl_module = hitl_client
    hitl_module.ensure_db()
    monkeypatch.setattr(hitl_module.random, "random", lambda: 0.0)

    candidate_1, label_result_1 = _create_candidate_and_label(
        hitl_module,
        "https://news.local/article-1",
        annotator_id="annotator-a",
    )
    _, label_result_2 = _create_candidate_and_label(
        hitl_module,
        "https://news.local/article-2",
        annotator_id="annotator-b",
    )

    qa_id_pending = label_result_1["qa_queue_id"]
    qa_id_pass = label_result_2["qa_queue_id"]
    assert qa_id_pending and qa_id_pass

    notes_text = "line1,with comma\nline2"
    reviewed_at = hitl_module.datetime.now(hitl_module.timezone.utc).isoformat()
    conn = sqlite3.connect(hitl_module.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE hitl_qa_queue SET review_status=?, reviewer_id=?, notes=?, reviewed_at=? WHERE id=?",
        ("pass", "reviewer-1", notes_text, reviewed_at, qa_id_pass),
    )
    conn.commit()
    conn.close()

    pending_resp = client.get("/api/qa/pending", params={"limit": 10})
    assert pending_resp.status_code == 200
    pending_data = pending_resp.json()
    assert pending_data["count"] == 1
    pending_item = pending_data["items"][0]
    assert pending_item["qa_id"] == qa_id_pending
    assert pending_item["review_status"] == "pending"
    assert pending_item["candidate_id"] == candidate_1
    assert pending_item["label"] == "valid_news"
    assert pending_item["extracted_text"] == "body"

    history_resp = client.get("/api/qa/history", params={"status": "pass", "limit": 5})
    assert history_resp.status_code == 200
    history_data = history_resp.json()
    assert history_data["count"] == 1
    history_item = history_data["items"][0]
    assert history_item["qa_id"] == qa_id_pass
    assert history_item["review_status"] == "pass"
    assert history_item["notes"] == notes_text
    assert history_item["reviewer_id"] == "reviewer-1"

    export_resp = client.get("/api/qa/export", params={"limit": 50})
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("text/csv")
    export_reader = csv.DictReader(StringIO(export_resp.text))
    export_rows = list(export_reader)
    assert len(export_rows) == 2
    export_pending = next(row for row in export_rows if row["qa_id"] == qa_id_pending)
    export_pass = next(row for row in export_rows if row["qa_id"] == qa_id_pass)
    assert export_pending["review_status"] == "pending"
    assert export_pending["label"] == "valid_news"
    assert export_pass["review_status"] == "pass"
    assert export_pass["notes"] == notes_text
    assert export_pass["cleaned_text"] == "clean text"
