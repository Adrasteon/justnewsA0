import importlib
import sqlite3
import sys
import uuid

import pytest


def _import_hitl_module(
    tmp_path, monkeypatch, extra_env: dict[str, str | None] | None = None
):
    db_path = tmp_path / f"hitl_ingest_{uuid.uuid4().hex}.db"
    monkeypatch.setenv("HITL_DB_PATH", str(db_path))

    # Reset forwarding env vars to avoid bleed between tests
    for var in (
        "HITL_FORWARD_AGENT",
        "HITL_FORWARD_TOOL",
        "HITL_CANDIDATE_FORWARD_AGENT",
        "HITL_CANDIDATE_FORWARD_TOOL",
        "HITL_TRAINING_FORWARD_AGENT",
        "HITL_TRAINING_FORWARD_TOOL",
    ):
        monkeypatch.delenv(var, raising=False)

    if extra_env:
        for key, value in extra_env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)

    module_name = "agents.hitl_service.app"
    sys.modules.pop(module_name, None)
    module = importlib.import_module(module_name)
    module.ensure_db()
    return module


@pytest.mark.asyncio
async def test_dispatch_ingest_calls_mcp_and_updates_db(tmp_path, monkeypatch):
    hitl_module = _import_hitl_module(
        tmp_path,
        monkeypatch,
        extra_env={
            "HITL_FORWARD_AGENT": "ingest-agent",
            "HITL_FORWARD_TOOL": "queue_article",
            "HITL_FORWARD_MAX_RETRIES": "2",
        },
    )

    captured: dict[str, object] = {}

    def _fake_call_tool(agent: str, tool: str, args, kwargs):  # noqa: ANN001
        captured["agent"] = agent
        captured["tool"] = tool
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"status": "ok"}

    monkeypatch.setattr(hitl_module.mcp_client, "call_tool", _fake_call_tool)

    # Insert a candidate and label it as valid to produce an ingest_payload
    candidate_id = str(uuid.uuid4())
    hitl_module.insert_candidate(
        hitl_module.CandidateEvent(
            id=candidate_id,
            url="https://news.test/article",
            site_id="test-site",
            extracted_text="body",
        )
    )

    label_req = hitl_module.LabelRequest(
        candidate_id=candidate_id,
        label="valid_news",
        cleaned_text="clean body",
        annotator_id="annotator-1",
    )
    result = hitl_module.store_label(label_req)

    assert result["enqueue_ingest"] is True
    ingest_payload = result["ingest_payload"]
    label_id = result["label_id"]

    status = await hitl_module.dispatch_ingest(ingest_payload, label_id)

    assert status == "enqueued"
    assert captured["agent"] == "ingest-agent"
    assert captured["tool"] == "queue_article"
    assert captured["args"] == []
    assert captured["kwargs"] == ingest_payload

    # Verify DB ingestion_status updated to 'enqueued' and ingest_enqueued_at set
    conn = sqlite3.connect(hitl_module.DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT ingestion_status, ingest_enqueued_at FROM hitl_labels WHERE id=?",
        (label_id,),
    )
    row = cur.fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "enqueued"
    assert row[1] is not None
