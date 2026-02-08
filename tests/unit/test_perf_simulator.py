import importlib.util


def test_simulate_concurrent_inference_dry_run(tmp_path, monkeypatch):
    # Force stubbed mode
    monkeypatch.setenv("RE_RANKER_TEST_MODE", "1")

    spec = importlib.util.spec_from_file_location(
        "simulate", "scripts/perf/simulate_concurrent_inference.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # run a tiny simulation and ensure output dict keys exist
    res = mod.run_workers(workers=2, total_requests=10, model_id=None)
    assert "total_requests" in res and res["total_requests"] == 10
    assert "gpu_used_after_mb" in res
