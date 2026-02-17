import pytest

from agents.common.adapter_base import AdapterError
from agents.common.mock_adapter import MockAdapter


def test_mock_adapter_basic_flow():
    adapter = MockAdapter(name="tst", latency_seconds=0)
    adapter.load("mock-model")
    health = adapter.health_check()
    assert health["loaded"] is True
    result = adapter.infer("hello world")
    assert result["text"].startswith("[MOCK:tst]")
    assert result["tokens"] >= 1
    assert result["raw"]["model_id"] == "mock-model"

    batch = adapter.batch_infer(["alpha", "beta"])
    assert len(batch) == 2
    assert batch[0]["text"].startswith("[MOCK:tst]")

    adapter.unload()
    assert adapter.health_check()["loaded"] is False


def test_mock_adapter_custom_responses_and_config():
    adapter = MockAdapter(
        name="cfg",
        responses={"hi": "Hello {prompt}"},
        default_text="Default:{prompt}:{count}",
        latency_seconds=0,
    )
    adapter.load(
        "model-x", config={"responses": {"bye": "Goodbye"}, "failure_prompts": ["fail"]}
    )
    assert adapter.infer("hi")["text"] == "Hello hi"
    assert adapter.infer("bye")["text"] == "Goodbye"
    assert adapter.infer("unknown")["text"].startswith("Default:unknown")

    with pytest.raises(AdapterError):
        adapter.infer("fail")


def test_mock_adapter_health_metadata_counts():
    adapter = MockAdapter(name="meta", latency_seconds=0)
    adapter.load(None)
    adapter.infer("ping")
    status = adapter.health_check()
    assert status["invocations"] == 1
    assert status["responses"] == 0
