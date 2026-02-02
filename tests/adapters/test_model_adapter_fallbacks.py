import pathlib

from agents.common.mistral_adapter import MistralAdapter


def _ms_root():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    return str(repo_root / "model_store")


def test_review_content_fallback_when_agent_returns_none(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_ROOT", _ms_root())
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    adapter = MistralAdapter(
        agent="chief_editor",
        adapter_name="mistral_chief_editor_v1",
        system_prompt="You are a mock.",
    )

    # simulate a per-agent implementation that returns None from review_content
    class FakeAgent:
        def review_content(self, content, metadata):
            return None

    adapter._agent_impl = FakeAgent()
    adapter.load(None)

    out = adapter.review_content(
        "Short copy to review", metadata={"assignment": "Budget"}
    )
    assert isinstance(out, dict)
    # fallback should produce either 'assessment' or 'priority' keys
    assert "assessment" in out or "priority" in out


def test_classify_returns_simulated_namespace_in_dryrun(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_ROOT", _ms_root())
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    adapter = MistralAdapter(
        agent="analyst",
        adapter_name="mistral_analyst_v1",
        system_prompt="You are a mock.",
    )
    # Should not need full load for classify dry-run path
    res = adapter.classify("This is a neutral test")
    assert res is not None
    # in dry-run we return a SimpleNamespace-like object with sentiment & bias
    assert hasattr(res, "sentiment") and hasattr(res, "bias")


def test_unload_clears_model_and_tokenizer(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_ROOT", _ms_root())
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    adapter = MistralAdapter(
        agent="synthesizer",
        adapter_name="mistral_synth_v1",
        system_prompt="You are a mock.",
    )
    adapter.load(None)
    # ensure load produced placeholders in dry-run
    assert adapter._base is not None
    assert isinstance(adapter._base.model, dict) or adapter._base.model is not None

    adapter.unload()
    # After unload, base model/tokenizer should be cleared
    assert adapter._base.model is None
    assert adapter._base.tokenizer is None
    health = adapter.health_check()
    assert isinstance(health, dict)
    assert health.get("available") is False
