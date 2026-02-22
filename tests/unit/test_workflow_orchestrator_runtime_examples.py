from agents.workflow_orchestrator.runtime_config import get_lane_policy_runtime_examples


def test_lane_policy_runtime_examples_shape():
    payload = get_lane_policy_runtime_examples()

    assert payload["owner"] == "workflow_orchestrator"
    assert "examples" in payload
    assert isinstance(payload["examples"], dict)

    required = {
        "enable_dev_baseline",
        "disable_safety_hold",
        "canary_tighten_thresholds",
        "sparse_topic_relief",
    }
    assert required.issubset(payload["examples"].keys())


def test_lane_policy_runtime_examples_keys_present():
    payload = get_lane_policy_runtime_examples()
    enable = payload["examples"]["enable_dev_baseline"]
    patch = enable["patch"]

    assert "orchestrator.lane_policy.enabled" in patch
    assert "orchestrator.lane_policy.min_article_count" in patch
    assert "orchestrator.lane_policy.min_source_count" in patch
    assert "orchestrator.lane_policy.min_unique_domains" in patch
    assert "orchestrator.lane_policy.version" in patch
