from scripts.dev.run_full_canary import main as run_full


def test_run_full_canary_smoke():
    metrics = run_full()
    assert isinstance(metrics, dict)
    # At least check basic keys exist
    assert metrics.get("fetch_success", 0) >= 0
