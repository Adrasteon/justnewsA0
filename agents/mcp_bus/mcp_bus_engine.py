"""
MCP Bus Engine - Core business logic for the Model Context Protocol Bus.

This engine handles agent registration, tool calling, circuit breaker logic,
and communication coordination between all JustNews agents.
"""

import os
import time
from typing import Any

from common.observability import get_logger

# Make 'requests' optional so MCP Bus can start in constrained environments.
try:
    import requests
except Exception:
    requests = None

logger = get_logger(__name__)


class MCPBusConfig:
    """Configuration for MCP Bus operations."""

    def __init__(self):
        self.connect_timeout = float(os.getenv("MCP_CALL_CONNECT_TIMEOUT", "3"))
        self.read_timeout = float(os.getenv("MCP_CALL_READ_TIMEOUT", "120"))
        self.circuit_breaker_fail_threshold = int(
            os.getenv("MCP_CB_FAIL_THRESHOLD", "3")
        )
        self.circuit_breaker_cooldown_sec = int(os.getenv("MCP_CB_COOLDOWN_SEC", "10"))
        self.max_retries = int(os.getenv("MCP_MAX_RETRIES", "3"))
        self.retry_backoff_base = float(os.getenv("MCP_RETRY_BACKOFF_BASE", "0.2"))


class MCPBusEngine:
    """
    Core engine for MCP Bus operations.

    Handles agent registration, tool calling, circuit breaker logic,
    and communication coordination between agents.
    """

    def __init__(self, config: MCPBusConfig | None = None):
        self.config = config or MCPBusConfig()
        self.agents: dict[str, str] = {}
        self.circuit_breaker_state: dict[str, dict[str, Any]] = {}
        self.logger = logger

    def register_agent(self, agent_name: str, agent_address: str) -> dict[str, str]:
        """
        Register an agent with the MCP Bus.

        Args:
            agent_name: Name of the agent to register
            agent_address: HTTP address of the agent

        Returns:
            Dict containing registration status
        """
        self.logger.info(f"Registering agent: {agent_name} at {agent_address}")
        self.agents[agent_name] = agent_address

        # Reset circuit breaker on registration
        self.circuit_breaker_state[agent_name] = {"fails": 0, "open_until": 0}

        return {"status": "ok"}

    def unregister_agent(self, agent_name: str) -> dict[str, str]:
        """
        Unregister an agent from the MCP Bus.

        Args:
            agent_name: Name of the agent to unregister

        Returns:
            Dict containing unregistration status
        """
        if agent_name in self.agents:
            self.logger.info(f"Unregistering agent: {agent_name}")
            del self.agents[agent_name]
            if agent_name in self.circuit_breaker_state:
                del self.circuit_breaker_state[agent_name]
            return {"status": "ok"}
        else:
            return {
                "status": "not_found",
                "message": f"Agent {agent_name} not registered",
            }

    def get_registered_agents(self) -> dict[str, str]:
        """
        Get all currently registered agents.

        Returns:
            Dict mapping agent names to their addresses
        """
        return self.agents.copy()

    def is_agent_registered(self, agent_name: str) -> bool:
        """
        Check if an agent is currently registered.

        Args:
            agent_name: Name of the agent to check

        Returns:
            True if agent is registered, False otherwise
        """
        return agent_name in self.agents

    def call_agent_tool(
        self, agent_name: str, tool_name: str, args: list, kwargs: dict
    ) -> dict[str, Any]:
        """
        Call a tool on a registered agent.

        Args:
            agent_name: Name of the agent to call
            tool_name: Name of the tool to execute
            args: Positional arguments for the tool
            kwargs: Keyword arguments for the tool

        Returns:
            Dict containing call result or error information

        Raises:
            ValueError: If agent is not registered or circuit breaker is open
            RuntimeError: If requests library is unavailable
            ConnectionError: If tool call fails after retries
        """
        if not self.is_agent_registered(agent_name):
            raise ValueError(f"Agent not found: {agent_name}")

        agent_address = self.agents[agent_name]

        # Check circuit breaker
        if self._is_circuit_breaker_open(agent_name):
            raise ValueError(f"Circuit breaker open for agent {agent_name}")

        if requests is None:
            raise RuntimeError("Requests library unavailable on host")

        payload = {"args": args, "kwargs": kwargs}
        url = f"{agent_address.rstrip('/')}/{tool_name.lstrip('/')}"
        timeout = (self.config.connect_timeout, self.config.read_timeout)

        # Execute tool call with retry logic
        return self._execute_tool_call(agent_name, url, payload, timeout)

    def _is_circuit_breaker_open(self, agent_name: str) -> bool:
        """
        Check if circuit breaker is open for an agent.

        Args:
            agent_name: Name of the agent to check

        Returns:
            True if circuit breaker is open, False otherwise
        """
        state = self.circuit_breaker_state.get(agent_name, {"open_until": 0})
        return state.get("open_until", 0) > time.time()

    def _execute_tool_call(
        self, agent_name: str, url: str, payload: dict, timeout: tuple
    ) -> dict[str, Any]:
        """
        Execute a tool call with retry logic and circuit breaker management.

        Args:
            agent_name: Name of the agent being called
            url: Full URL for the tool call
            payload: JSON payload to send
            timeout: Connection and read timeouts

        Returns:
            Dict containing call result

        Raises:
            ConnectionError: If all retry attempts fail
        """
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                response = requests.post(url, json=payload, timeout=timeout)
                response.raise_for_status()

                # Success: reset circuit breaker
                self.circuit_breaker_state[agent_name] = {"fails": 0, "open_until": 0}

                return {"status": "success", "data": response.json()}

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                self.logger.warning(
                    f"Tool call attempt {attempt + 1} failed for {agent_name}: {e}"
                )

                # Exponential backoff
                if attempt < self.config.max_retries - 1:
                    backoff_time = self.config.retry_backoff_base * (2**attempt)
                    time.sleep(backoff_time)

        # All retries failed: update circuit breaker
        self._handle_call_failure(agent_name, last_error)
        raise ConnectionError(
            f"Tool call failed after {self.config.max_retries} attempts: {last_error}"
        )

    def _handle_call_failure(self, agent_name: str, error: str) -> None:
        """
        Handle a tool call failure by updating circuit breaker state.

        Args:
            agent_name: Name of the agent that failed
            error: Error message from the failure
        """
        fails = self.circuit_breaker_state.get(agent_name, {}).get("fails", 0) + 1

        if fails >= self.config.circuit_breaker_fail_threshold:
            # Open circuit breaker
            open_until = time.time() + self.config.circuit_breaker_cooldown_sec
            self.circuit_breaker_state[agent_name] = {
                "fails": 0,
                "open_until": open_until,
            }
            self.logger.warning(
                f"Circuit breaker opened for {agent_name} for {self.config.circuit_breaker_cooldown_sec}s "
                f"after {fails} failures"
            )
        else:
            self.circuit_breaker_state[agent_name] = {"fails": fails, "open_until": 0}

    def get_circuit_breaker_status(self) -> dict[str, dict[str, Any]]:
        """
        Get the current circuit breaker status for all agents.

        Returns:
            Dict mapping agent names to their circuit breaker state
        """
        return self.circuit_breaker_state.copy()

    def notify_gpu_orchestrator(self) -> bool:
        """
        Notify the GPU Orchestrator that MCP Bus is ready.

        Returns:
            True if notification succeeded, False otherwise
        """
        if requests is None:
            self.logger.warning(
                "Requests library not available; skipping GPU Orchestrator notification"
            )
            return False

        orchestrator_url = "http://localhost:8014/notify_ready"

        try:
            response = requests.post(orchestrator_url, timeout=10)
            response.raise_for_status()
            self.logger.info(
                "Successfully notified GPU Orchestrator that MCP Bus is ready"
            )
            return True
        except requests.RequestException as e:
            self.logger.error(f"Failed to notify GPU Orchestrator: {e}")
            return False

    def get_health_status(self) -> dict[str, Any]:
        """
        Get comprehensive health status of the MCP Bus.

        This includes probing registered agents' /health endpoints (when
        the requests library is available) and returning per-agent status
        and response times. If requests is unavailable, agent health will
        be reported as 'unknown'.

        Returns:
            Dict containing health information
        """
        # Basic status
        circuit_active = any(
            state.get("open_until", 0) > time.time()
            for state in self.circuit_breaker_state.values()
        )

        # Probe registered agents for their health (best-effort)
        agent_details: list[dict[str, Any]] = []
        any_unhealthy = False

        if not self.agents:
            # No agents registered
            return {
                "status": "degraded",
                "registered_agents": 0,
                "circuit_breaker_active": circuit_active,
                "agent_details": [],
                "timestamp": time.time(),
            }

        if requests is None:
            # Can't perform HTTP probes without requests
            for name in self.agents.keys():
                agent_details.append(
                    {"agent": name, "status": "unknown", "reason": "requests_unavailable"}
                )
        else:
            for name, address in self.agents.items():
                url = address.rstrip("/") + "/health"
                try:
                    start = time.time()
                    resp = requests.get(url, timeout=1.0)
                    elapsed = time.time() - start

                    if resp.ok:
                        # Try to parse JSON overall_status if present
                        status = "healthy"
                        try:
                            data = resp.json()
                            if isinstance(data, dict) and "overall_status" in data:
                                status = data.get("overall_status") or status
                        except Exception:
                            # Ignore JSON parse errors — still consider OK
                            pass

                        agent_details.append(
                            {"agent": name, "status": status, "response_time": round(elapsed, 4)}
                        )
                        if status != "healthy":
                            any_unhealthy = True
                    else:
                        agent_details.append(
                            {"agent": name, "status": "unhealthy", "status_code": resp.status_code}
                        )
                        any_unhealthy = True

                except Exception as e:
                    agent_details.append(
                        {"agent": name, "status": "unreachable", "error": str(e)}
                    )
                    any_unhealthy = True

        overall = "healthy"
        issues = []
        if circuit_active:
            overall = "degraded"
            issues.append("Circuit breaker active for one or more agents")
        if any_unhealthy:
            overall = "degraded"
            issues.append("One or more registered agents reported unhealthy or unreachable")

        return {
            "status": overall,
            "registered_agents": len(self.agents),
            "circuit_breaker_active": circuit_active,
            "agent_details": agent_details,
            "issues": issues,
            "timestamp": time.time(),
        }

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about MCP Bus operations.

        Returns:
            Dict containing operational statistics
        """
        total_failures = sum(
            state.get("fails", 0) for state in self.circuit_breaker_state.values()
        )

        open_circuits = sum(
            1
            for state in self.circuit_breaker_state.values()
            if state.get("open_until", 0) > time.time()
        )

        return {
            "registered_agents": len(self.agents),
            "total_circuit_breaker_failures": total_failures,
            "open_circuits": open_circuits,
            "agents_with_failures": len(
                [
                    agent
                    for agent, state in self.circuit_breaker_state.items()
                    if state.get("fails", 0) > 0
                ]
            ),
        }
