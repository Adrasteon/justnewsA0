import os

from agents.workflow_orchestrator.engine import OrchestratorEngine


def test_apply_runtime_overrides_sets_lane_policy_env(monkeypatch):
    monkeypatch.setattr(OrchestratorEngine, "_init_policies", lambda self: None)
    monkeypatch.setattr(OrchestratorEngine, "_load_config", lambda self: setattr(self, "config", {}))

    engine = OrchestratorEngine()

    monkeypatch.delenv("MULTI_SOURCE_LANE_POLICY_ENABLED", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_MIN_SOURCE_COUNT", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_MIN_UNIQUE_DOMAINS", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_LANE_POLICY_VERSION", raising=False)

    result = engine.apply_runtime_overrides(
        {
            "orchestrator.lane_policy.enabled": False,
            "orchestrator.lane_policy.min_source_count": 3,
            "orchestrator.lane_policy.min_unique_domains": 4,
            "orchestrator.lane_policy.version": "v-runtime-test",
        }
    )

    applied = result.get("applied", {})
    assert "orchestrator.lane_policy.enabled" in applied
    assert "orchestrator.lane_policy.min_source_count" in applied
    assert "orchestrator.lane_policy.min_unique_domains" in applied
    assert "orchestrator.lane_policy.version" in applied

    assert os.environ["MULTI_SOURCE_LANE_POLICY_ENABLED"] == "0"
    assert os.environ["MULTI_SOURCE_MIN_SOURCE_COUNT"] == "3"
    assert os.environ["MULTI_SOURCE_MIN_UNIQUE_DOMAINS"] == "4"
    assert os.environ["MULTI_SOURCE_LANE_POLICY_VERSION"] == "v-runtime-test"


def test_apply_runtime_overrides_ignores_non_orchestrator(monkeypatch):
    monkeypatch.setattr(OrchestratorEngine, "_init_policies", lambda self: None)
    monkeypatch.setattr(OrchestratorEngine, "_load_config", lambda self: setattr(self, "config", {}))
    engine = OrchestratorEngine()

    result = engine.apply_runtime_overrides({"fact_checker.search.max_queries": 8})
    assert result["applied"] == {}
    assert result["ignored"]["fact_checker.search.max_queries"] == 8
