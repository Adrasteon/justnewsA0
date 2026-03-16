import os

from agents.workflow_orchestrator.engine import OrchestratorEngine
from agents.workflow_orchestrator.policies import _derive_publication_lane_metadata


def test_apply_runtime_overrides_sets_lane_policy_env(monkeypatch):
    monkeypatch.setattr(OrchestratorEngine, "_init_policies", lambda self: None)
    monkeypatch.setattr(OrchestratorEngine, "_load_config", lambda self: setattr(self, "config", {}))

    engine = OrchestratorEngine()

    monkeypatch.delenv("MULTI_SOURCE_LANE_POLICY_ENABLED", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_LANE1_ENABLED", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_LANE2_ENABLED", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_MIN_ARTICLE_COUNT", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_MIN_SOURCE_COUNT", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_MIN_UNIQUE_DOMAINS", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_LANE_POLICY_VERSION", raising=False)
    monkeypatch.delenv("MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON", raising=False)

    result = engine.apply_runtime_overrides(
        {
            "orchestrator.lane_policy.enabled": False,
            "orchestrator.lane_policy.lane1_enabled": True,
            "orchestrator.lane_policy.lane2_enabled": False,
            "orchestrator.lane_policy.min_article_count": 2,
            "orchestrator.lane_policy.min_source_count": 3,
            "orchestrator.lane_policy.min_unique_domains": 4,
            "orchestrator.lane_policy.version": "v-runtime-test",
            "orchestrator.lane_policy.topic_overrides_json": '{"breaking":{"min_source_count":1}}',
        }
    )

    applied = result.get("applied", {})
    assert "orchestrator.lane_policy.enabled" in applied
    assert "orchestrator.lane_policy.lane1_enabled" in applied
    assert "orchestrator.lane_policy.lane2_enabled" in applied
    assert "orchestrator.lane_policy.min_article_count" in applied
    assert "orchestrator.lane_policy.min_source_count" in applied
    assert "orchestrator.lane_policy.min_unique_domains" in applied
    assert "orchestrator.lane_policy.version" in applied
    assert "orchestrator.lane_policy.topic_overrides_json" in applied

    assert os.environ["MULTI_SOURCE_LANE_POLICY_ENABLED"] == "0"
    assert os.environ["MULTI_SOURCE_LANE1_ENABLED"] == "1"
    assert os.environ["MULTI_SOURCE_LANE2_ENABLED"] == "0"
    assert os.environ["MULTI_SOURCE_MIN_ARTICLE_COUNT"] == "2"
    assert os.environ["MULTI_SOURCE_MIN_SOURCE_COUNT"] == "3"
    assert os.environ["MULTI_SOURCE_MIN_UNIQUE_DOMAINS"] == "4"
    assert os.environ["MULTI_SOURCE_LANE_POLICY_VERSION"] == "v-runtime-test"
    assert os.environ["MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON"] == '{"breaking":{"min_source_count":1}}'


def test_apply_runtime_overrides_ignores_non_orchestrator(monkeypatch):
    monkeypatch.setattr(OrchestratorEngine, "_init_policies", lambda self: None)
    monkeypatch.setattr(OrchestratorEngine, "_load_config", lambda self: setattr(self, "config", {}))
    engine = OrchestratorEngine()

    result = engine.apply_runtime_overrides({"fact_checker.search.max_queries": 8})
    assert result["applied"] == {}
    assert result["ignored"]["fact_checker.search.max_queries"] == 8


def test_apply_runtime_overrides_clears_removed_lane_keys(monkeypatch):
    monkeypatch.setattr(OrchestratorEngine, "_init_policies", lambda self: None)
    monkeypatch.setattr(OrchestratorEngine, "_load_config", lambda self: setattr(self, "config", {}))
    engine = OrchestratorEngine()

    monkeypatch.setenv(
        "MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON",
        '{"breaking":{"min_article_count":1}}',
    )

    result = engine.apply_runtime_overrides({"orchestrator.lane_policy.enabled": True})

    assert "orchestrator.lane_policy.enabled" in result["applied"]
    assert "MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON" not in os.environ


def test_runtime_override_changes_lane_decision(monkeypatch):
    monkeypatch.setattr(OrchestratorEngine, "_init_policies", lambda self: None)
    monkeypatch.setattr(OrchestratorEngine, "_load_config", lambda self: setattr(self, "config", {}))

    engine = OrchestratorEngine()

    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_ENABLED", "1")
    monkeypatch.setenv("MULTI_SOURCE_MIN_ARTICLE_COUNT", "2")
    monkeypatch.setenv("MULTI_SOURCE_MIN_SOURCE_COUNT", "2")
    monkeypatch.setenv("MULTI_SOURCE_MIN_UNIQUE_DOMAINS", "2")

    before = _derive_publication_lane_metadata(
        cluster_id="CL-RUNTIME-1",
        article_count=1,
        input_fingerprint="abcdef0123456789",
        context_metrics={
            "source_count": 1,
            "unique_domain_count": 1,
            "fact_quality_score": 0.72,
        },
        urgency_class="breaking",
    )
    assert before["publication_lane"] == "developing_brief"

    engine.apply_runtime_overrides(
        {
            "orchestrator.lane_policy.enabled": True,
            "orchestrator.lane_policy.topic_overrides_json": '{"breaking":{"min_article_count":1,"min_source_count":1,"min_unique_domains":1}}',
        }
    )

    after = _derive_publication_lane_metadata(
        cluster_id="CL-RUNTIME-1",
        article_count=1,
        input_fingerprint="abcdef0123456789",
        context_metrics={
            "source_count": 1,
            "unique_domain_count": 1,
            "fact_quality_score": 0.72,
        },
        urgency_class="breaking",
    )

    assert after["publication_lane"] == "verified_story"
    assert after["policy_override_source"] == "topic_override:breaking"


def test_runtime_override_lane2_disabled_bounces_to_lane1(monkeypatch):
    monkeypatch.setattr(OrchestratorEngine, "_init_policies", lambda self: None)
    monkeypatch.setattr(OrchestratorEngine, "_load_config", lambda self: setattr(self, "config", {}))

    engine = OrchestratorEngine()
    engine.apply_runtime_overrides(
        {
            "orchestrator.lane_policy.enabled": True,
            "orchestrator.lane_policy.lane1_enabled": True,
            "orchestrator.lane_policy.lane2_enabled": False,
            "orchestrator.lane_policy.min_article_count": 2,
            "orchestrator.lane_policy.min_source_count": 2,
            "orchestrator.lane_policy.min_unique_domains": 2,
        }
    )

    result = _derive_publication_lane_metadata(
        cluster_id="CL-BOUNCE-1",
        article_count=1,
        input_fingerprint="abcdef0123456789",
        context_metrics={
            "source_count": 1,
            "unique_domain_count": 1,
            "fact_quality_score": 0.6,
        },
    )

    assert result["publication_lane"] == "verified_story"
    assert "lane2_disabled_bounced_to_lane1" in result["decision_reason_codes"]
