import importlib
import sys
import types

from fastapi.testclient import TestClient


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
