import os

from agents.common.model_loader import (
    get_agent_model_metadata,
    load_transformers_with_adapter,
)


def test_model_store_dry_run_resolves_agent_paths(monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    # point to the in-repo model_store for testing
    ms_root = os.path.join(repo_root, "model_store")
    monkeypatch.setenv("MODEL_STORE_ROOT", ms_root)
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    # Choose an agent present in AGENT_MODEL_MAP.json
    agent = "synthesizer"
    adapter_name = "mistral_synth_v1"

    model, adapter = load_transformers_with_adapter(agent, adapter_name)
    assert isinstance(model, dict) or model is not None
    assert isinstance(adapter, dict) or adapter is not None

    metadata = get_agent_model_metadata(agent, adapter_name)
    assert metadata is not None
    assert metadata.get("base_info") is not None
