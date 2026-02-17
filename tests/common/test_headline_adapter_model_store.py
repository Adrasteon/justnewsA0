from __future__ import annotations

from pathlib import Path

import pytest

from agents.common import headline_adapter as headline_module


class _FakeOpenAIAdapter:
    created: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeOpenAIAdapter.created.append(kwargs)

    def ensure_loaded(self):
        return None

    def infer(self, prompt: str):
        return {"text": "{\"headlines\": [\"Neutral headline one\", \"Neutral headline two\", \"Neutral headline three\"]}"}


def test_headline_adapter_uses_model_store_metadata(monkeypatch, tmp_path: Path):
    adapter_path = tmp_path / "chief_editor/adapters/qwen2_headline_v1"
    adapter_path.mkdir(parents=True)

    def _fake_get_agent_model_metadata(agent: str, adapter_name: str):
        assert agent == "chief_editor"
        assert adapter_name == "qwen2_headline_v1"
        return {
            "adapter_path": adapter_path,
            "base_info": {"hf_id": "Qwen/Qwen2.5-14B-Instruct-AWQ"},
        }

    import agents.common.model_loader as model_loader

    monkeypatch.setattr(model_loader, "get_agent_model_metadata", _fake_get_agent_model_metadata)
    monkeypatch.setattr(headline_module, "OpenAIAdapter", _FakeOpenAIAdapter)
    monkeypatch.setenv("VLLM_ENABLE_LORA", "true")
    _FakeOpenAIAdapter.created.clear()
    headline_module.HeadlineAdapter._adapter_cache.clear()

    adapter = headline_module.HeadlineAdapter(name="headline_test")
    adapter.get_llm_adapter()

    assert _FakeOpenAIAdapter.created
    created = _FakeOpenAIAdapter.created[-1]
    assert created["model"] == "qwen2_headline_v1"
    assert str(created["extra_headers"]["x-justnews-adapter-path"]).endswith(
        "chief_editor/adapters/qwen2_headline_v1"
    )


def test_headline_adapter_strict_model_store_requires_adapter_path(monkeypatch):
    def _fake_get_agent_model_metadata(agent: str, adapter_name: str):
        return {"adapter_path": None, "base_info": {"hf_id": "Qwen/Qwen2.5-14B-Instruct-AWQ"}}

    import agents.common.model_loader as model_loader

    monkeypatch.setattr(model_loader, "get_agent_model_metadata", _fake_get_agent_model_metadata)
    monkeypatch.setenv("STRICT_MODEL_STORE", "1")
    monkeypatch.setenv("VLLM_ENABLE_LORA", "true")
    headline_module.HeadlineAdapter._adapter_cache.clear()

    adapter = headline_module.HeadlineAdapter(name="headline_strict_test")
    with pytest.raises(RuntimeError):
        adapter.get_llm_adapter()
