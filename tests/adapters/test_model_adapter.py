import pathlib

from agents.common.mistral_adapter import MistralAdapter


def test_mistral_adapter_dry_run(monkeypatch):
    # Ensure dry-run uses model_store dry-run and local model_store path
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    ms_root = str(repo_root / "model_store")
    monkeypatch.setenv("MODEL_STORE_ROOT", ms_root)
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    adapter = MistralAdapter(
        agent="synthesizer",
        adapter_name="mistral_synth_v1",
        system_prompt="You are a mock.",
    )
    adapter.load(None)
    health = adapter.health_check()
    assert isinstance(health, dict)
    assert "available" in health

    out = adapter.infer("Hello world from test")
    assert isinstance(out, dict) and "text" in out

    batch = adapter.batch_infer(["a", "b"])
    assert isinstance(batch, list) and len(batch) == 2

    # cluster-level dry-run summary
    doc = adapter.summarize_cluster(
        ["Article one content", "Article two content"], context="testing"
    )
    assert isinstance(doc, dict)
    assert "summary" in doc and isinstance(doc["summary"], str)
