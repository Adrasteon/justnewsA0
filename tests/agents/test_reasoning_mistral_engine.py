from agents.reasoning.reasoning_engine import ReasoningConfig, ReasoningEngine


def test_reasoning_engine_mistral_dry_run(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    engine = ReasoningEngine(ReasoningConfig())

    res = engine._run_llm_analysis("Is water wet?")

    assert res is not None
    assert isinstance(res, dict)
    assert "verdict" in res
