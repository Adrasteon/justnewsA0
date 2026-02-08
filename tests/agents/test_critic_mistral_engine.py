from agents.critic.critic_engine import CriticConfig, CriticEngine


def test_critic_engine_mistral_dry_run(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    engine = CriticEngine(CriticConfig())

    res = engine._maybe_run_mistral_review(
        "Sample article content for critic.", url="https://example.com"
    )

    assert res is not None
    # result should be a ReviewResult-like object with an overall_score
    assert hasattr(res, "overall_score")
