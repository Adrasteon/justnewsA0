
import pytest

try:
    import requests
except Exception:
    requests = None

from agents.mcp_bus.mcp_bus_engine import MCPBusEngine


class DummyResp:
    def __init__(self, ok=True, status_code=200, json_data=None):
        self.ok = ok
        self.status_code = status_code
        self._json = json_data or {"overall_status": "healthy"}

    def json(self):
        return self._json


def test_get_health_status_probes_agents_monkeypatched(monkeypatch):
    engine = MCPBusEngine()
    engine.agents = {"mock_agent": "http://localhost:9999"}

    # Simulate a healthy agent response
    def fake_get(url, timeout):
        assert url.endswith("/health")
        return DummyResp(ok=True, status_code=200, json_data={"overall_status": "healthy"})

    monkeypatch.setattr("agents.mcp_bus.mcp_bus_engine.requests.get", fake_get)

    health = engine.get_health_status()

    assert health["registered_agents"] == 1
    assert isinstance(health.get("agent_details"), list)
    assert health["agent_details"][0]["agent"] == "mock_agent"
    assert health["agent_details"][0]["status"] == "healthy"
    assert health["status"] == "healthy"


def test_get_health_status_marks_unreachable_agents(monkeypatch):
    engine = MCPBusEngine()
    engine.agents = {"bad_agent": "http://localhost:9998"}

    # Simulate requests.get raising an exception
    def fake_get(url, timeout):
        raise requests.exceptions.RequestException("connection refused")

    if requests is None:
        pytest.skip("requests not available in this environment")

    monkeypatch.setattr("agents.mcp_bus.mcp_bus_engine.requests.get", fake_get)

    health = engine.get_health_status()

    assert health["registered_agents"] == 1
    assert health["status"] == "degraded"
    assert any(a["status"] in ("unreachable", "unhealthy") for a in health["agent_details"])


def test_get_health_status_agent_reports_degraded(monkeypatch):
    """When an agent returns overall_status != 'healthy', the bus marks it degraded."""
    engine = MCPBusEngine()
    engine.agents = {"bad_agent": "http://localhost:9998"}

    # Simulate an agent returning a degraded overall_status
    def fake_get(url, timeout):
        assert url.endswith("/health")
        return DummyResp(ok=True, status_code=200, json_data={"overall_status": "degraded"})

    if requests is None:
        pytest.skip("requests not available in this environment")

    monkeypatch.setattr("agents.mcp_bus.mcp_bus_engine.requests.get", fake_get)

    health = engine.get_health_status()

    assert health["registered_agents"] == 1
    assert health["status"] == "degraded"
    assert any(a.get("status") == "degraded" for a in health["agent_details"])


def test_health_check_emits_metrics(monkeypatch):
    """Assert that health_check() emits JustNewsMetrics health updates."""
    calls = []

    class FakeMetrics:
        def __init__(self, name):
            self.name = name

        def set_health_status(self, status, target="overall", agent=None, response_time=None):
            calls.append({"status": status, "target": target, "agent": agent})

    # Ensure there are two agents and patch requests to return healthy for one and unreachable for another
    from agents.mcp_bus import tools
    engine = tools.get_engine()
    engine.agents = {"good_agent": "http://localhost:9999", "bad_agent": "http://localhost:9998"}

    def fake_get(url, timeout):
        if url.endswith("9999/health"):
            return DummyResp(ok=True, status_code=200, json_data={"overall_status": "healthy"})
        raise Exception("connection refused")

    monkeypatch.setattr("agents.mcp_bus.mcp_bus_engine.requests.get", fake_get)
    monkeypatch.setattr("common.metrics.JustNewsMetrics", FakeMetrics)

    from agents.mcp_bus import tools

    res = tools.health_check()

    # Expect overall set + per-agent sets
    assert any(c["target"] == "overall" for c in calls)
    assert any(c["target"] == "per_agent" for c in calls)
    # Ensure at least one per-agent call includes an agent label
    assert any(c.get("agent") for c in calls if c.get("target") == "per_agent")
    assert res["overall_status"] == "degraded"
