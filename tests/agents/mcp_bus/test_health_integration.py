from fastapi.testclient import TestClient

from agents.mcp_bus import tools
from agents.mcp_bus.main import app


def setup_function():
    # Ensure a clean engine state before each test
    engine = tools.get_engine()
    engine.agents.clear()
    engine.circuit_breaker_state.clear()


def test_health_endpoint_no_agents(monkeypatch):
    # Prevent startup notification from making external requests
    monkeypatch.setattr("agents.mcp_bus.main.notify_gpu_orchestrator", lambda: True)

    client = TestClient(app)
    res = client.get("/health")

    assert res.status_code == 200

    payload = res.json()
    assert "overall_status" in payload
    # When no agents are registered, overall_status should be degraded
    assert payload["overall_status"] == "degraded"
    assert payload["components"]["agents"]["registered_agents"] == 0


def test_health_endpoint_with_agent_probe(monkeypatch):
    # Prevent startup notification from making external requests
    monkeypatch.setattr("agents.mcp_bus.main.notify_gpu_orchestrator", lambda: True)

    # Register a mock agent in the engine
    engine = tools.get_engine()
    engine.agents.clear()
    engine.agents["mock_agent"] = "http://localhost:9999"

    # Patch the requests.get used by the engine to return a healthy response
    class FakeResp:
        def __init__(self):
            self.ok = True
            self.status_code = 200

        def json(self):
            return {"overall_status": "healthy"}


    def fake_get(url, timeout=1.0):
        assert url.endswith("/health")
        return FakeResp()

    monkeypatch.setattr("agents.mcp_bus.mcp_bus_engine.requests.get", fake_get)

    client = TestClient(app)
    res = client.get("/health")

    assert res.status_code == 200
    payload = res.json()

    assert payload["overall_status"] == "healthy"
    agents_comp = payload["components"]["agents"]
    assert agents_comp["registered_agents"] == 1
    details = agents_comp["details"]
    assert len(details) == 1
    assert details[0]["agent"] == "mock_agent"
    assert details[0]["status"] == "healthy"


def test_health_endpoint_agent_reports_degraded(monkeypatch):
    """Agent returns an overall_status of 'degraded' and MCP Bus should reflect that."""
    monkeypatch.setattr("agents.mcp_bus.main.notify_gpu_orchestrator", lambda: True)

    engine = tools.get_engine()
    engine.agents.clear()
    engine.agents["bad_agent"] = "http://localhost:9998"

    class BadResp:
        def __init__(self):
            self.ok = True
            self.status_code = 200

        def json(self):
            return {"overall_status": "degraded"}

    def fake_get(url, timeout=1.0):
        assert url.endswith("/health")
        return BadResp()

    monkeypatch.setattr("agents.mcp_bus.mcp_bus_engine.requests.get", fake_get)

    client = TestClient(app)
    res = client.get("/health")

    assert res.status_code == 200
    payload = res.json()

    # MCP Bus should mark overall status as degraded and agents component degraded
    assert payload["overall_status"] == "degraded"
    agents_comp = payload["components"]["agents"]
    assert agents_comp["registered_agents"] == 1
    details = agents_comp["details"]
    assert len(details) == 1
    assert details[0]["agent"] == "bad_agent"
    assert details[0]["status"] == "degraded"
