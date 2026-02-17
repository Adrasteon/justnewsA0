from agents.journalist.journalist_engine import JournalistEngine


def test_journalist_engine_mistral_dry_run(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    engine = JournalistEngine()

    payload = {
        "markdown": "Test article about local news.",
        "title": "Local test",
        "url": "https://example.com",
    }
    brief = engine._generate_llm_brief(payload)

    assert brief is not None
    assert isinstance(brief, dict)
    assert "headline" in brief or "summary" in brief
