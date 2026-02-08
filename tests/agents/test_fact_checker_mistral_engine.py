from agents.fact_checker.fact_checker_engine import FactCheckerConfig, FactCheckerEngine


def test_fact_checker_engine_mistral_dry_run(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    engine = FactCheckerEngine(FactCheckerConfig())

    assessment = engine._evaluate_with_mistral(
        "The Eiffel Tower is in Paris.", context="geography"
    )

    assert assessment is not None
    # Verify expected attributes on the result
    assert hasattr(assessment, "verdict")
    assert hasattr(assessment, "confidence")
