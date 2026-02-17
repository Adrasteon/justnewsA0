# MCP Bus Health and Diagnostics

This document explains the MCP Bus `/health`and`/ready` endpoints, how health is reported, how to interpret results,
and developer guidance for adding tests covering health behaviour.

## Overview

The MCP Bus exposes a machine-readable health endpoint at `/health` (HTTP GET). It performs best-effort probes against
registered agents' `/health` endpoints and returns a composite status that includes per-agent details, circuit breaker
state, and operational issues.

- Endpoint: `GET http://<mcp_host>:<mcp_port>/health`

- Readiness endpoint: `GET /ready`returns`{"ready": true|false}` (service ready flag).

The endpoint is intended for operational checks, health monitoring, and load balancers.

## Response schema

A typical `/health` JSON body includes:

- `timestamp`: Unix timestamp

- `overall_status`:`healthy`|`degraded`|`unhealthy`

- `registered_agents`: number of agents known to the bus

- `circuit_breaker_active`: boolean (true if one or more breakers are open)

- `agent_details`: list of per-agent objects:

- `agent`: agent name

- `status`:`healthy`|`degraded`|`unhealthy`|`unreachable`|`unknown`

- `response_time`: seconds (float, optional)

- `status_code`: HTTP response code (optional)

- `error`: error message on probe failure (optional)

- `issues`: array of strings describing any global issues

Example:

```json
{
  "timestamp": 1690000000.1234,
  "overall_status": "degraded",
  "registered_agents": 3,
  "circuit_breaker_active": false,
  "agent_details": [
    {"agent": "analyst", "status": "healthy", "response_time": 0.042},
    {"agent": "synthesizer", "status": "unreachable", "error": "connect timeout"}
  ],
  "issues": ["One or more registered agents reported unhealthy or unreachable"]
}

```bash

## How the probe works (developer notes)

- The MCP Bus engine performs a best-effort HTTP GET to `<agent_address>/health`(1s probe timeout) for each registered
  agent when`requests` is available.

- If `requests`is not importable, agent statuses will be set to`unknown`and the bus-level`overall_status`may
  be`degraded` if agents are expected.

- Any non-2xx response, JSON parse error, or network error will be reported as `unhealthy`/`unreachable`and will mark
  the bus`overall_status`as`degraded`.

- Circuit breakers are included in the health report (see `circuit_breaker_active` boolean).

## Operational usage (user)

- Quick health check (local):

```bash
curl -s <http://localhost:8017/health> | jq

```

- Confirm readiness:

```bash
curl -s <http://localhost:8017/ready> && echo "MCP Bus ready"

```bash

- The repository provides a multi-service health check script used by operators in
  `infrastructure/systemd/health_check.sh`which already includes`mcp_bus` in the default services list.

## Monitoring & alerting

- Add an alert on `overall_status != "healthy"`for key services. For example, alert when`mcp_bus`reports`degraded`or
  when a specific agent is`unreachable` for more than 2 check cycles.

- Integrate the endpoint into your Prometheus blackbox exporter or a simple cron job for internal monitoring.

## Testing (developer)

### Unit tests

- The engine-level logic is in `agents/mcp_bus/mcp_bus_engine.py`.

- Unit tests for the engine live in `tests/agents/mcp_bus/test_health.py` and cover:

- Unreachable agents (requests exceptions)

- Agents reporting `degraded`statuses (non-`healthy` JSON)

Run the unit tests in the canonical environment:

```bash
conda run -n ${CANONICAL_ENV:-justnews-py312-phase1} pytest -q tests/agents/mcp_bus/test_health.py

```

### Integration tests

- Integration tests exercise the FastAPI app (TestClient) and live at `tests/agents/mcp_bus/test_health_integration.py`.

- These tests patch `requests.get`to simulate agent responses and
  monkeypatch`agents.mcp_bus.main.notify_gpu_orchestrator` to prevent external network calls during app startup.

Run integration tests:

```bash
conda run -n ${CANONICAL_ENV:-justnews-py312-phase1} pytest -q tests/agents/mcp_bus/test_health_integration.py

```

### Writing tests

- Prefer `monkeypatch`to patch`agents.mcp_bus.mcp_bus_engine.requests.get` when simulating agent responses.

- For FastAPI endpoint tests use `fastapi.testclient.TestClient(app)`and ensure the engine state is clean before each
  test by clearing`tools.get_engine().agents`and`circuit_breaker_state`.

- Patch `agents.mcp_bus.main.notify_gpu_orchestrator`(returning`True`) in tests that instantiate the`TestClient` to
  avoid network calls during the app lifespan.

Example test patterns are included in the `tests/agents/mcp_bus` directory.

## Troubleshooting

- If `/health`reports`unreachable` for a known agent:

- Verify the agent is registered (GET `/agents`).

- Check the agent's own `/health` endpoint directly (curl).

- Confirm network/firewall rules allow `MCP Bus` to connect to the agent address.

- If health checks appear slow, check whether `requests` is falling back to slow DNS lookups or whether the probe
  timeout is too large; the probe timeout defaults to 1.0s per agent.

## Files of interest

- `agents/mcp_bus/main.py` — FastAPI endpoints

- `agents/mcp_bus/tools.py`— tool wrappers and`health_check()` helper

- `agents/mcp_bus/mcp_bus_engine.py` — engine implementation and probe logic

- `infrastructure/systemd/health_check.sh` — operational multi-service script used by operators

- `tests/agents/mcp_bus/test_health.py` — unit tests

- `tests/agents/mcp_bus/test_health_integration.py` — FastAPI integration tests

---

If you want, I can add example Prometheus alert rules and a short Grafana panel for MCP Bus health. Let me know if you'd
like that included.
