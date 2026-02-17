from agents.common.hf_adapter import HFAdapter
from agents.common.openai_adapter import OpenAIAdapter
from common.metrics import get_metrics


def test_openai_dryrun_emits_metrics(monkeypatch):
    # Ensure dry-run and metrics increments are recorded
    monkeypatch.setenv("DRY_RUN", "1")
    a = OpenAIAdapter(api_key=None, name="openai-metrics-test", model="gpt-x")
    a.load(None)
    # call infer (dry-run) should record metrics in registry
    _ = a.infer("Testing metrics")
    metrics = get_metrics("openai-metrics-test")
    # underlying metrics should now contain our custom histogram & counter
    assert "openai_infer_latency_seconds" in metrics._custom_histograms
    assert "openai_infer_success" in metrics._custom_counters


def test_hf_dryrun_emits_metrics(monkeypatch):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")
    a = HFAdapter(model_name="gpt-test", name="hf-metrics-test")
    a.load(None)
    _ = a.infer("hello")
    metrics = get_metrics("hf-metrics-test")
    assert "hf_infer_latency_seconds" in metrics._custom_histograms
    assert "hf_infer_success" in metrics._custom_counters
