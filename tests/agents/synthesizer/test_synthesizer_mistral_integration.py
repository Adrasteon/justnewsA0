from agents.synthesizer.synthesizer_engine import SynthesizerEngine


def test_synthesizer_engine_mistral_dry_run(monkeypatch):
    # ensure dry-run mode so we don't attempt heavy weights
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    engine = SynthesizerEngine()

    # provide a long-ish article and call the internal frag
    text = "This is a test article used for dry-run mistral summarize"
    res = engine._summarize_with_mistral(text)

    # should return a SynthesisResult with a simulated summary in dry-run
    assert res is not None
    assert hasattr(res, "content")
    assert res.success is True
    assert "DRYRUN-synthesizer" in res.content or (
        isinstance(res.metadata.get("mistral"), dict)
        and "Simulated" in res.metadata["mistral"].get("summary", "")
    )
