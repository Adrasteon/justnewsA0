from __future__ import annotations

import importlib
from pathlib import Path

import pytest

triage_module = importlib.import_module('agents.common.triage_adapter')


class _FakeOpenAIAdapter:
    created: list[dict] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeOpenAIAdapter.created.append(kwargs)

    def ensure_loaded(self):
        return None

    def infer(self, prompt: str):
        return {'text': '{"decision":"accept","confidence":0.88,"page_type":"article","reason_codes":["article_like_content"]}'}


def test_triage_adapter_uses_model_store_metadata(monkeypatch, tmp_path: Path):
    adapter_path = tmp_path / 'crawler_triage/adapters/qwen2_crawler_triage_v1'
    adapter_path.mkdir(parents=True)

    def _fake_get_agent_model_metadata(agent: str, adapter_name: str):
        assert agent == 'crawler_triage'
        assert adapter_name == 'qwen2_crawler_triage_v1'
        return {
            'adapter_path': adapter_path,
            'base_info': {'hf_id': 'Qwen/Qwen2.5-14B-Instruct-AWQ'},
        }

    import agents.common.model_loader as model_loader

    monkeypatch.setattr(model_loader, 'get_agent_model_metadata', _fake_get_agent_model_metadata)
    monkeypatch.setattr(triage_module, 'OpenAIAdapter', _FakeOpenAIAdapter)
    monkeypatch.setenv('VLLM_ENABLE_LORA', 'true')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_ENABLED', '1')
    _FakeOpenAIAdapter.created.clear()
    triage_module.TriageAdapter._adapter_cache.clear()

    adapter = triage_module.TriageAdapter(name='triage_test')
    adapter.get_llm_adapter()

    assert _FakeOpenAIAdapter.created
    created = _FakeOpenAIAdapter.created[-1]
    assert created['model'] == 'qwen2_crawler_triage_v1'
    assert str(created['extra_headers']['x-justnews-adapter-path']).endswith(
        'crawler_triage/adapters/qwen2_crawler_triage_v1'
    )


def test_triage_adapter_strict_model_store_requires_adapter_path(monkeypatch):
    def _fake_get_agent_model_metadata(agent: str, adapter_name: str):
        return {'adapter_path': None, 'base_info': {'hf_id': 'Qwen/Qwen2.5-14B-Instruct-AWQ'}}

    import agents.common.model_loader as model_loader

    monkeypatch.setattr(model_loader, 'get_agent_model_metadata', _fake_get_agent_model_metadata)
    monkeypatch.setenv('STRICT_MODEL_STORE', '1')
    monkeypatch.setenv('VLLM_ENABLE_LORA', 'true')
    monkeypatch.setenv('CRAWL4AI_AI_TRIAGE_ENABLED', '1')
    triage_module.TriageAdapter._adapter_cache.clear()

    adapter = triage_module.TriageAdapter(name='triage_strict_test')
    with pytest.raises(RuntimeError):
        adapter.get_llm_adapter()
