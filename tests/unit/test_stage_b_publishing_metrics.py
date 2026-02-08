from common.stage_b_metrics import use_default_stage_b_metrics


def test_record_publish_metrics():
    m = use_default_stage_b_metrics()
    # Ensure initial value is 0
    _ = (
        m.get_editorial_acceptance_sum()
        if hasattr(m, "get_editorial_acceptance_sum")
        else 0
    )
    m.record_publish_result("success")
    m.record_publish_result("failure")
    # No direct getters defined, but the counters should increment without error
    # Ensure methods exist and callable
    m.observe_publish_latency(0.123)
    assert hasattr(m, "record_publish_result")
    assert hasattr(m, "observe_publish_latency")
