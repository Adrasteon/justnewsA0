import importlib
import os
import sys
import time
import types

from fastapi.testclient import TestClient
from agents.workflow_orchestrator.policies import (
    _derive_publication_lane_metadata,
    _record_cluster_promotion_failure_metrics,
    _record_lane_metrics,
    _record_singleton_to_verified_conversion,
)


def _load_main_with_stubs(monkeypatch):
    fake_engine_module = types.ModuleType("agents.workflow_orchestrator.engine")

    class DummyEngine:
        def __init__(self):
            self.running = False
            self.config = {
                "polling_interval_seconds": 10,
                "max_concurrent_tasks": 5,
                "resource_limits": {
                    "max_cpu_percent": 95,
                    "max_memory_percent": 98,
                    "max_gpu_utilization": 95,
                    "max_gpu_memory_percent": 95,
                },
            }

        async def start(self):
            return None

        async def stop(self):
            return None

        def attach_runtime_store(self, _runtime_store):
            return None

        def apply_runtime_overrides(self, overrides):
            return {"applied": dict(overrides), "ignored": {}}

    fake_engine_module.OrchestratorEngine = DummyEngine
    monkeypatch.setitem(sys.modules, "agents.workflow_orchestrator.engine", fake_engine_module)

    fake_db_module = types.ModuleType("database.utils.migrated_database_utils")

    def _fake_create_database_service(*_args, **_kwargs):
        return object()

    def _fake_get_db_config():
        return {}

    fake_db_module.create_database_service = _fake_create_database_service
    fake_db_module.get_db_config = _fake_get_db_config
    monkeypatch.setitem(sys.modules, "database.utils.migrated_database_utils", fake_db_module)

    fake_mcp_module = types.ModuleType("agents.common.mcp_bus_client")

    class DummyMCPBusClient:
        def __init__(self, base_url=None):
            self.base_url = base_url

        def register_agent(self, **_kwargs):
            return None

    fake_mcp_module.MCPBusClient = DummyMCPBusClient
    monkeypatch.setitem(sys.modules, "agents.common.mcp_bus_client", fake_mcp_module)

    module_name = "agents.workflow_orchestrator.main"
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_runtime_config_get_and_validate_endpoints(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        get_resp = client.get("/runtime-config")
        assert get_resp.status_code == 200
        payload = get_resp.json()

        assert payload["status"] == "ok"
        assert "orchestrator.lane_policy.min_article_count" in payload["registry"]
        assert "orchestrator.lane_policy.lane1_enabled" in payload["registry"]
        assert "orchestrator.lane_policy.lane2_enabled" in payload["registry"]
        assert payload["config_version"] == 0
        assert 0 in payload["available_versions"]

        validate_resp = client.post(
            "/runtime-config/validate",
            json={
                "patch": {
                    "orchestrator.lane_policy.enabled": "true",
                    "orchestrator.lane_policy.min_article_count": "2",
                }
            },
        )
        assert validate_resp.status_code == 200
        validated = validate_resp.json()
        assert validated["status"] == "ok"
        assert validated["ok"] is True
        assert validated["normalized"]["orchestrator.lane_policy.enabled"] is True
        assert validated["normalized"]["orchestrator.lane_policy.min_article_count"] == 2


def test_runtime_config_apply_and_rollback_endpoints(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        apply_resp = client.patch(
            "/runtime-config",
            json={
                "patch": {
                    "orchestrator.lane_policy.enabled": True,
                    "orchestrator.lane_policy.min_article_count": 2,
                    "orchestrator.lane_policy.min_source_count": 2,
                    "orchestrator.lane_policy.min_unique_domains": 2,
                    "orchestrator.lane_policy.version": "v-ctrl-plane",
                },
                "reason": "integration apply",
                "actor": "test",
            },
        )
        assert apply_resp.status_code == 200
        applied = apply_resp.json()
        assert applied["status"] == "ok"
        assert applied["owner"] == "workflow_orchestrator"
        assert applied["owner_apply_result"]["applied"]["orchestrator.lane_policy.version"] == "v-ctrl-plane"

        version_after_apply = int(applied["version"])
        rollback_resp = client.post(
            "/runtime-config/rollback",
            json={
                "target_version": 0,
                "reason": "integration rollback",
                "actor": "test",
            },
        )
        assert rollback_resp.status_code == 200
        rolled = rollback_resp.json()
        assert rolled["status"] == "ok"
        assert rolled["previous_version"] == version_after_apply
        assert rolled["rollback_target_version"] == 0
        assert rolled["owner"] == "workflow_orchestrator"


def test_runtime_config_actuation_and_apply_rollback_endpoints(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        bad_tier = client.post(
            "/runtime-config/actuate",
            json={
                "tier": "tier1",
                "patch": {"fact_checker.search.max_queries": 7},
                "reason": "invalid tier patch",
                "actor": "test",
            },
        )
        assert bad_tier.status_code == 400

        act_resp = client.post(
            "/runtime-config/actuate",
            json={
                "tier": "tier1",
                "patch": {
                    "orchestrator.lane_policy.enabled": True,
                    "orchestrator.lane_policy.topic_overrides_json": '{"breaking":{"min_article_count":1,"min_source_count":1,"min_unique_domains":1}}',
                },
                "reason": "tier actuation",
                "actor": "test",
            },
        )
        assert act_resp.status_code == 200
        acted = act_resp.json()
        assert acted["status"] == "ok"
        assert acted["tier"] == "tier1"

        apply_version = int(acted["version"])
        rollback_apply_resp = client.post(
            "/runtime-config/actuate/rollback",
            json={
                "apply_version": apply_version,
                "reason": "rollback apply version",
                "actor": "test",
            },
        )
        assert rollback_apply_resp.status_code == 200
        rolled = rollback_apply_resp.json()
        assert rolled["status"] == "ok"
        assert rolled["inverse_of_apply_version"] == apply_version
        assert rolled["owner"] == "workflow_orchestrator"


def test_runtime_config_validate_reports_errors_for_invalid_patch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        response = client.post(
            "/runtime-config/validate",
            json={
                "patch": {
                    "orchestrator.unknown.key": 1,
                    "orchestrator.lane_policy.min_article_count": 0,
                }
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["ok"] is False
    assert any("Unknown runtime key" in err for err in payload["errors"])
    assert any("below minimum" in err for err in payload["errors"])


def test_runtime_config_apply_requires_reason(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        response = client.patch(
            "/runtime-config",
            json={
                "patch": {"orchestrator.lane_policy.enabled": True},
                "reason": "",
                "actor": "test",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "reason is required"


def test_runtime_config_apply_rejects_unknown_and_non_hot_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        unknown_key = client.patch(
            "/runtime-config",
            json={
                "patch": {"orchestrator.lane_policy.not_real": 1},
                "reason": "unknown key",
                "actor": "test",
            },
        )
        assert unknown_key.status_code == 400
        detail = unknown_key.json()["detail"]
        assert detail["status"] == "error"
        assert any("Unknown runtime key" in err for err in detail["errors"])

        non_hot = client.patch(
            "/runtime-config",
            json={
                "patch": {"analyst.workers": 3},
                "reason": "non-hot key",
                "actor": "test",
            },
        )
        assert non_hot.status_code == 400
        detail = non_hot.json()["detail"]
        assert detail["status"] == "error"
        assert "runtime apply rejected" in detail["errors"][0]
        assert "analyst.workers" in detail["blocked_non_hot"]


def test_runtime_config_rollback_errors(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        missing_reason = client.post(
            "/runtime-config/rollback",
            json={"target_version": 999, "reason": "", "actor": "test"},
        )
        assert missing_reason.status_code == 400
        assert missing_reason.json()["detail"] == "reason is required"

        bad_target = client.post(
            "/runtime-config/rollback",
            json={"target_version": 999, "reason": "bad target", "actor": "test"},
        )
        assert bad_target.status_code == 400
        detail = bad_target.json()["detail"]
        assert detail["status"] == "error"
        assert "not found" in detail["message"]


def test_runtime_config_actuate_and_rollback_error_paths(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        missing_reason = client.post(
            "/runtime-config/actuate",
            json={
                "tier": "tier1",
                "patch": {"orchestrator.lane_policy.enabled": True},
                "reason": "",
                "actor": "test",
            },
        )
        assert missing_reason.status_code == 400
        assert missing_reason.json()["detail"] == "reason is required"

        unknown_tier = client.post(
            "/runtime-config/actuate",
            json={
                "tier": "tier9",
                "patch": {"orchestrator.lane_policy.enabled": True},
                "reason": "unknown tier",
                "actor": "test",
            },
        )
        assert unknown_tier.status_code == 400
        detail = unknown_tier.json()["detail"]
        assert detail["status"] == "error"
        assert "unknown tier" in detail["errors"][0]

        rollback_missing_reason = client.post(
            "/runtime-config/actuate/rollback",
            json={"apply_version": 1, "reason": "", "actor": "test"},
        )
        assert rollback_missing_reason.status_code == 400
        assert rollback_missing_reason.json()["detail"] == "reason is required"

        rollback_unknown_apply = client.post(
            "/runtime-config/actuate/rollback",
            json={
                "apply_version": 123,
                "reason": "unknown apply",
                "actor": "test",
            },
        )
        assert rollback_unknown_apply.status_code == 400
        detail = rollback_unknown_apply.json()["detail"]
        assert detail["status"] == "error"
        assert "not found" in detail["message"]


def test_metrics_endpoint_exposes_lane_observability_contract(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    _record_lane_metrics(
        {
            "publication_lane": "verified_story",
            "unique_domain_count": 3,
        }
    )
    _record_cluster_promotion_failure_metrics(
        {
            "publication_lane": "developing_brief",
            "decision_reason_codes": ["insufficient_source_count"],
        }
    )
    _record_singleton_to_verified_conversion(
        story_id="STORY-METRICS-1",
        prev_meta={"publication": {"publication_lane": "developing_brief"}},
        lane_metadata={"publication_lane": "verified_story"},
    )

    with TestClient(main_mod.app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    assert "justnews_custom_counter_published_total_verified_story" in body
    assert "justnews_custom_gauge_published_verified_share" in body
    assert "justnews_custom_gauge_median_unique_domains_per_story" in body
    assert "justnews_custom_counter_cluster_promotion_failures_insufficient_source_count" in body
    assert "justnews_custom_counter_singleton_to_verified_conversion_total" in body


def test_runtime_rollback_sla_and_lane_revert(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_ENABLED", "1")
    monkeypatch.setenv("MULTI_SOURCE_LANE1_ENABLED", "1")
    monkeypatch.setenv("MULTI_SOURCE_LANE2_ENABLED", "1")
    monkeypatch.setenv("MULTI_SOURCE_MIN_ARTICLE_COUNT", "2")
    monkeypatch.setenv("MULTI_SOURCE_MIN_SOURCE_COUNT", "2")
    monkeypatch.setenv("MULTI_SOURCE_MIN_UNIQUE_DOMAINS", "2")
    monkeypatch.setenv("MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON", "")

    lane_env_map = {
        "orchestrator.lane_policy.enabled": "MULTI_SOURCE_LANE_POLICY_ENABLED",
        "orchestrator.lane_policy.lane1_enabled": "MULTI_SOURCE_LANE1_ENABLED",
        "orchestrator.lane_policy.lane2_enabled": "MULTI_SOURCE_LANE2_ENABLED",
        "orchestrator.lane_policy.min_article_count": "MULTI_SOURCE_MIN_ARTICLE_COUNT",
        "orchestrator.lane_policy.min_source_count": "MULTI_SOURCE_MIN_SOURCE_COUNT",
        "orchestrator.lane_policy.min_unique_domains": "MULTI_SOURCE_MIN_UNIQUE_DOMAINS",
        "orchestrator.lane_policy.version": "MULTI_SOURCE_LANE_POLICY_VERSION",
        "orchestrator.lane_policy.topic_overrides_json": "MULTI_SOURCE_LANE_POLICY_TOPIC_OVERRIDES_JSON",
    }

    def _apply_runtime_overrides(overrides):
        applied = {}
        ignored = {}
        for runtime_key, env_key in lane_env_map.items():
            if runtime_key not in overrides:
                os.environ.pop(env_key, None)
        for key, value in overrides.items():
            env_key = lane_env_map.get(key)
            if env_key is None:
                ignored[key] = value
                continue
            if isinstance(value, bool):
                os.environ[env_key] = "1" if value else "0"
            else:
                os.environ[env_key] = str(value)
            applied[key] = value
        return {"applied": applied, "ignored": ignored}

    main_mod.engine.apply_runtime_overrides = _apply_runtime_overrides

    before = _derive_publication_lane_metadata(
        cluster_id="CL-SLA-1",
        article_count=1,
        input_fingerprint="abcdef0123456789",
        context_metrics={
            "source_count": 1,
            "unique_domain_count": 1,
            "fact_quality_score": 0.7,
        },
        urgency_class="breaking",
    )
    assert before["publication_lane"] == "developing_brief"

    with TestClient(main_mod.app) as client:
        apply_start = time.monotonic()
        apply_resp = client.patch(
            "/runtime-config",
            json={
                "patch": {
                    "orchestrator.lane_policy.enabled": True,
                    "orchestrator.lane_policy.topic_overrides_json": '{"breaking":{"min_article_count":1,"min_source_count":1,"min_unique_domains":1}}',
                },
                "reason": "sla apply",
                "actor": "test",
            },
        )
        apply_duration_sec = time.monotonic() - apply_start
        assert apply_resp.status_code == 200
        assert apply_duration_sec <= 3.0
        apply_payload = apply_resp.json()
        assert apply_payload["status"] == "ok"

        after_apply = _derive_publication_lane_metadata(
            cluster_id="CL-SLA-1",
            article_count=1,
            input_fingerprint="abcdef0123456789",
            context_metrics={
                "source_count": 1,
                "unique_domain_count": 1,
                "fact_quality_score": 0.7,
            },
            urgency_class="breaking",
        )
        assert after_apply["publication_lane"] == "verified_story"

        rollback_start = time.monotonic()
        rollback_resp = client.post(
            "/runtime-config/rollback",
            json={
                "target_version": 0,
                "reason": "sla rollback",
                "actor": "test",
            },
        )
        rollback_duration_sec = time.monotonic() - rollback_start
        assert rollback_resp.status_code == 200
        assert rollback_duration_sec <= 3.0

    after_rollback = _derive_publication_lane_metadata(
        cluster_id="CL-SLA-1",
        article_count=1,
        input_fingerprint="abcdef0123456789",
        context_metrics={
            "source_count": 1,
            "unique_domain_count": 1,
            "fact_quality_score": 0.7,
        },
        urgency_class="breaking",
    )
    assert after_rollback["publication_lane"] == "developing_brief"
