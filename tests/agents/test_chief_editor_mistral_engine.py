from agents.chief_editor.chief_editor_engine import ChiefEditorConfig, ChiefEditorEngine


def test_chief_editor_engine_mistral_dry_run(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    engine = ChiefEditorEngine(ChiefEditorConfig())

    res = engine.mistral_adapter.review_content(
        "Short copy to review", metadata={"assignment": "Budget"}
    )

    assert res is not None
    assert isinstance(res, dict)
    assert "priority" in res or "assessment" in res
