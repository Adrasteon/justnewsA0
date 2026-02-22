from agents.workflow_orchestrator.policies import (
    _derive_publication_lane_metadata,
    _record_cluster_promotion_failure_metrics,
    _record_lane_metrics,
    _record_singleton_to_verified_conversion,
)
import agents.workflow_orchestrator.policies as policies


def test_lane_metadata_verified_story(monkeypatch):
    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_ENABLED", "1")
    monkeypatch.setenv("MULTI_SOURCE_MIN_SOURCE_COUNT", "2")
    monkeypatch.setenv("MULTI_SOURCE_MIN_UNIQUE_DOMAINS", "2")
    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_VERSION", "v-test")

    result = _derive_publication_lane_metadata(
        cluster_id="CL-123",
        article_count=3,
        input_fingerprint="abcdef0123456789fedcba",
        context_metrics={
            "source_count": 3,
            "unique_domain_count": 3,
            "fact_quality_score": 0.82,
        },
    )

    assert result["publication_lane"] == "verified_story"
    assert result["confidence_tier"] == "high"
    assert result["policy_version"] == "v-test"
    assert result["decision_reason_codes"] == ["meets_multi_source_thresholds"]
    assert result["provenance_trace_id"].startswith("cluster:CL-123:")


def test_lane_metadata_developing_brief_with_reason_codes(monkeypatch):
    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_ENABLED", "1")
    monkeypatch.setenv("MULTI_SOURCE_MIN_SOURCE_COUNT", "2")
    monkeypatch.setenv("MULTI_SOURCE_MIN_UNIQUE_DOMAINS", "2")

    result = _derive_publication_lane_metadata(
        cluster_id="CL-456",
        article_count=1,
        input_fingerprint="1234567890abcdef123456",
        context_metrics={
            "source_count": 1,
            "unique_domain_count": 1,
            "fact_quality_score": 0.55,
        },
    )

    assert result["publication_lane"] == "developing_brief"
    assert result["confidence_tier"] == "low"
    assert "single_article_cluster" in result["decision_reason_codes"]
    assert "insufficient_source_count" in result["decision_reason_codes"]
    assert "insufficient_domain_diversity" in result["decision_reason_codes"]


def test_lane_metadata_policy_disabled(monkeypatch):
    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_ENABLED", "0")

    result = _derive_publication_lane_metadata(
        cluster_id="CL-789",
        article_count=4,
        input_fingerprint="fedcba9876543210fedcba",
        context_metrics={
            "source_count": 4,
            "unique_domain_count": 4,
            "fact_quality_score": 0.90,
        },
    )

    assert result["publication_lane"] == "developing_brief"
    assert result["policy_enabled"] is False
    assert result["decision_reason_codes"] == ["lane_policy_disabled"]


def test_lane_metadata_topic_override_applies(monkeypatch):
    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_ENABLED", "1")
    monkeypatch.setenv("MULTI_SOURCE_MIN_SOURCE_COUNT", "2")
    monkeypatch.setenv("MULTI_SOURCE_MIN_UNIQUE_DOMAINS", "2")
    monkeypatch.setenv(
        "MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON",
        '{"breaking": {"min_article_count": 1, "min_source_count": 1, "min_unique_domains": 1}}',
    )

    result = _derive_publication_lane_metadata(
        cluster_id="CL-999",
        article_count=1,
        input_fingerprint="999999abcdef",
        context_metrics={
            "source_count": 1,
            "unique_domain_count": 1,
            "fact_quality_score": 0.65,
        },
        urgency_class="breaking",
    )

    assert result["publication_lane"] == "verified_story"
    assert result["policy_override_source"] == "topic_override:breaking"
    assert result["policy_thresholds"]["min_source_count"] == 1
    assert result["policy_thresholds"]["min_unique_domains"] == 1


def test_record_lane_metrics_updates_counters_and_share(monkeypatch):
    class _MetricSpy:
        def __init__(self):
            self.counters = []
            self.gauges = {}

        def increment(self, metric_name: str, amount: float = 1.0):
            self.counters.append((metric_name, amount))

        def gauge(self, metric_name: str, value: float):
            self.gauges[metric_name] = value

    spy = _MetricSpy()
    monkeypatch.setattr(policies, "_ORCH_METRICS", spy)
    monkeypatch.setattr(
        policies,
        "_LANE_METRIC_TOTALS",
        {"verified_story": 0, "developing_brief": 0},
    )
    monkeypatch.setattr(policies, "_UNIQUE_DOMAIN_SAMPLES", [])

    _record_lane_metrics(
        {
            "publication_lane": "verified_story",
            "unique_domain_count": 3,
        }
    )
    _record_lane_metrics(
        {
            "publication_lane": "developing_brief",
            "unique_domain_count": 1,
        }
    )

    assert ("published_total_verified_story", 1.0) in spy.counters
    assert ("published_total_developing_brief", 1.0) in spy.counters
    assert spy.gauges["published_verified_share"] == 0.5
    assert spy.gauges["median_unique_domains_per_story"] == 2.0


def test_record_cluster_promotion_failure_metrics_emits_reason_counters(monkeypatch):
    class _MetricSpy:
        def __init__(self):
            self.counters = []

        def increment(self, metric_name: str, amount: float = 1.0):
            self.counters.append((metric_name, amount))

        def gauge(self, metric_name: str, value: float):
            pass

    spy = _MetricSpy()
    monkeypatch.setattr(policies, "_ORCH_METRICS", spy)

    _record_cluster_promotion_failure_metrics(
        {
            "publication_lane": "developing_brief",
            "decision_reason_codes": [
                "insufficient_source_count",
                "insufficient_domain_diversity",
            ],
        }
    )

    assert ("cluster_promotion_failures_insufficient_source_count", 1.0) in spy.counters
    assert ("cluster_promotion_failures_insufficient_domain_diversity", 1.0) in spy.counters


def test_singleton_to_verified_conversion_emits_once_per_story(monkeypatch):
    class _MetricSpy:
        def __init__(self):
            self.counters = []

        def increment(self, metric_name: str, amount: float = 1.0):
            self.counters.append((metric_name, amount))

        def gauge(self, metric_name: str, value: float):
            pass

    spy = _MetricSpy()
    monkeypatch.setattr(policies, "_ORCH_METRICS", spy)
    monkeypatch.setattr(policies, "_SINGLETON_CONVERSION_SEEN", set())

    prev_meta = {"publication": {"publication_lane": "developing_brief"}}
    lane_metadata = {"publication_lane": "verified_story"}

    _record_singleton_to_verified_conversion(
        story_id="STORY-1",
        prev_meta=prev_meta,
        lane_metadata=lane_metadata,
    )
    _record_singleton_to_verified_conversion(
        story_id="STORY-1",
        prev_meta=prev_meta,
        lane_metadata=lane_metadata,
    )

    matches = [x for x in spy.counters if x[0] == "singleton_to_verified_conversion_total"]
    assert len(matches) == 1
