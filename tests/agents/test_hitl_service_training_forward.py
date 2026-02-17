import asyncio
import importlib
import sys
import uuid

import pytest


def _import_hitl_module(
    tmp_path, monkeypatch, extra_env: dict[str, str | None] | None = None
):
    db_path = tmp_path / f"hitl_training_{uuid.uuid4().hex}.db"
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


def test_store_label_returns_training_payload(tmp_path, monkeypatch):
    hitl_module = _import_hitl_module(tmp_path, monkeypatch)
    monkeypatch.setattr(hitl_module.random, "random", lambda: 0.99)

    candidate_id = str(uuid.uuid4())
    event = hitl_module.CandidateEvent(
        id=candidate_id,
        url="https://news.local/story",
        site_id="test-site",
        extracted_text="body",
    )
    hitl_module.insert_candidate(event)

    req = hitl_module.LabelRequest(
        candidate_id=candidate_id,
        label="messy_news",
        cleaned_text="cleaned",
        annotator_id="annotator-42",
    )
    result = hitl_module.store_label(req)

    training_payload = result.get("training_payload")
    assert training_payload is not None
    assert training_payload["label_id"] == result["label_id"]
    assert training_payload["label"] == "messy_news"
    assert training_payload["treat_as_valid"] is True
    assert training_payload["needs_cleanup"] is True
    assert training_payload["qa_sampled"] is False
    assert training_payload["candidate"]["id"] == candidate_id
    assert training_payload["ingestion_status"] == "pending"


@pytest.mark.asyncio
async def test_forward_training_label_calls_mcp(tmp_path, monkeypatch):
    hitl_module = _import_hitl_module(
        tmp_path,
        monkeypatch,
        extra_env={
            "HITL_TRAINING_FORWARD_AGENT": "training-agent",
            "HITL_TRAINING_FORWARD_TOOL": "publish_label",
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

    payload = {"label_id": "label-1", "label": "valid_news"}
    status = await hitl_module.forward_training_label(payload, "label-1")

    assert status == "sent"
    assert captured["agent"] == "training-agent"
    assert captured["tool"] == "publish_label"
    assert captured["args"] == []
    assert captured["kwargs"] == payload


@pytest.mark.asyncio
async def test_training_forward_flow_updates_metrics(tmp_path, monkeypatch):
    hitl_module = _import_hitl_module(
        tmp_path,
        monkeypatch,
        extra_env={
            "HITL_TRAINING_FORWARD_AGENT": "training_system",
            "HITL_TRAINING_FORWARD_TOOL": "receive_hitl_label",
        },
    )
    monkeypatch.setattr(hitl_module.random, "random", lambda: 0.99)

    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, package=None: None
        if name == "transformers"
        else original_find_spec(name, package),
    )

    training_coordinator_module = importlib.import_module(
        "training_system.core.training_coordinator"
    )
    training_system_manager = importlib.import_module(
        "training_system.core.system_manager"
    )
    training_mcp = importlib.import_module("training_system.mcp_integration")

    # Reset shared singletons to guarantee a fresh state for monitoring assertions
    training_system_manager._training_manager = None  # type: ignore[attr-defined]
    training_coordinator_module.training_coordinator = None
    training_mcp.training_metrics = training_mcp.TrainingMetrics()

    manager = training_system_manager.get_system_training_manager()
    if manager.coordinator:
        manager.coordinator.training_buffers.get("fact_checker", []).clear()

    def _counter_value() -> float:
        counter = hitl_module.metrics._custom_counters.get(
            "hitl_training_forward_success_total"
        )
        if not counter:
            return 0.0
        child = counter.labels(
            agent=hitl_module.metrics.agent_name,
            agent_display_name=hitl_module.metrics.display_name,
        )
        return child._value.get()

    counter_before = _counter_value()
    metric_before = training_mcp.training_metrics.training_examples_total.labels(
        agent="training_system",
        agent_display_name=training_mcp.training_metrics.display_name,
        example_type="hitl_label",
        example_type_display_name="hitl-label",
    )._value.get()

    # Delegate MCP call into the training service endpoint
    def _call_tool(agent: str, tool: str, args, kwargs):  # noqa: ANN001
        assert agent == "training_system"
        assert tool == "receive_hitl_label"
        payload_obj = training_mcp.HitlLabelPayload.model_validate(kwargs)
        return asyncio.run(training_mcp.receive_hitl_label(payload_obj))

    monkeypatch.setattr(hitl_module.mcp_client, "call_tool", _call_tool)

    candidate_id = str(uuid.uuid4())
    hitl_module.insert_candidate(
        hitl_module.CandidateEvent(
            id=candidate_id,
            url="https://news.local/monitor",
            site_id="monitor-site",
            extracted_text="body",
        )
    )

    label_req = hitl_module.LabelRequest(
        candidate_id=candidate_id,
        label="valid_news",
        cleaned_text="clean body",
        annotator_id="annotator-monitor",
    )
    result = hitl_module.store_label(label_req)

    await hitl_module.forward_training_label(
        result["training_payload"], result["label_id"]
    )

    counter_after = _counter_value()
    metric_after = training_mcp.training_metrics.training_examples_total.labels(
        agent="training_system",
        agent_display_name=training_mcp.training_metrics.display_name,
        example_type="hitl_label",
        example_type_display_name="hitl-label",
    )._value.get()

    buffer = manager.coordinator.training_buffers["fact_checker"]

    assert counter_after == pytest.approx(counter_before + 1.0)
    assert metric_after == pytest.approx(metric_before + 1.0)
    assert len(buffer) == 1
