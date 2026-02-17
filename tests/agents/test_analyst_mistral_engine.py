from agents.analyst.analyst_engine import AnalystEngine


def test_analyst_engine_mistral_dry_run(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    engine = AnalystEngine()

    res = engine._get_mistral_result("This is an Analyst test text.")

    assert res is not None
    # result expected to have sentiment and bias attributes
    assert hasattr(res, "sentiment") and hasattr(res, "bias")
