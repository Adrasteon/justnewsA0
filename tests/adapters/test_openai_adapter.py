from agents.common.openai_adapter import OpenAIAdapter


def test_openai_adapter_dry_run(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    a = OpenAIAdapter(
        api_key=None, model="gpt-test", name="test-openai", system_prompt="hi"
    )
    # load should succeed in dry-run
    a.load(None)
    h = a.health_check()
    assert h["loaded"] is True
    assert h["model"] == "gpt-test"

    out = a.infer("Hello from dry-run OpenAI")
    assert isinstance(out, dict)
    assert out.get("raw", {}).get("simulated") is True

    batch = a.batch_infer(["a", "b"])
    assert isinstance(batch, list) and len(batch) == 2
