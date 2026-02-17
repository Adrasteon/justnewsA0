from agents.common.hf_adapter import HFAdapter


def test_hf_adapter_dry_run(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")
    a = HFAdapter(model_name="gpt-test", name="test-hf")
    a.load(None)
    h = a.health_check()
    assert h["loaded"] is True
    assert h["model_id"] == "gpt-test"

    out = a.infer("hello world")
    assert isinstance(out, dict)
    assert out.get("raw", {}).get("simulated") is True

    batch = a.batch_infer(["x", "y"])
    assert isinstance(batch, list) and len(batch) == 2


def test_hf_adapter_quantization_helpers(monkeypatch):
    adapter = HFAdapter(model_name="local-model", name="hf-q", quantization="8bit")
    kwargs = adapter._quantization_kwargs()
    assert kwargs.get("load_in_8bit") is True
    assert adapter.metadata()["quantization"] == "int8"
