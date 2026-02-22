import importlib
import sys
import types

from fastapi.testclient import TestClient


def _load_main_with_stubs(monkeypatch):
    fake_engine_module = types.ModuleType("agents.workflow_orchestrator.engine")

    class DummyEngine:
        def __init__(self):
            self.running = False
            self.config = {}

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


def test_runtime_config_examples_endpoint_shape(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    main_mod = _load_main_with_stubs(monkeypatch)

    with TestClient(main_mod.app) as client:
        response = client.get("/runtime-config/examples")

    assert response.status_code == 200
    payload = response.json()

    assert payload.get("status") == "ok"
    examples = payload.get("examples", {})
    assert examples.get("owner") == "workflow_orchestrator"

    example_map = examples.get("examples", {})
    assert "enable_dev_baseline" in example_map
    assert "disable_safety_hold" in example_map
    assert "canary_tighten_thresholds" in example_map
    assert "sparse_topic_relief" in example_map
