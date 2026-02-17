"""
MCP Bus Tools - Core functionality for agent communication and coordination.

This module provides the main tool functions for the MCP Bus agent,
handling agent registration, tool calling, and communication coordination.
"""

import time
from typing import Any

from common.observability import get_logger

from .mcp_bus_engine import MCPBusConfig, MCPBusEngine

logger = get_logger(__name__)

# Global engine instance
_engine: MCPBusEngine = None


def get_engine() -> MCPBusEngine:
    """Get the global MCP Bus engine instance."""
    global _engine
    if _engine is None:
        _engine = MCPBusEngine(MCPBusConfig())
    return _engine


def register_agent(agent_name: str, agent_address: str) -> dict[str, str]:
    """
    Register an agent with the MCP Bus.

    Args:
        agent_name: Name of the agent to register
        agent_address: HTTP address of the agent

    Returns:
        Dict containing registration status
    """
    try:
        engine = get_engine()
        result = engine.register_agent(agent_name, agent_address)
        logger.info(f"Agent {agent_name} registered successfully at {agent_address}")
        return result
    except Exception as e:
        logger.error(f"Failed to register agent {agent_name}: {e}")
        raise


def unregister_agent(agent_name: str) -> dict[str, str]:
    """
    Unregister an agent from the MCP Bus.

    Args:
        agent_name: Name of the agent to unregister

    Returns:
        Dict containing unregistration status
    """
    try:
        engine = get_engine()
        result = engine.unregister_agent(agent_name)
        if result["status"] == "ok":
            logger.info(f"Agent {agent_name} unregistered successfully")
        else:
            logger.warning(
                f"Agent {agent_name} unregistration: {result.get('message', 'unknown status')}"
            )
        return result
    except Exception as e:
        logger.error(f"Failed to unregister agent {agent_name}: {e}")
        raise


def call_agent_tool(
    agent_name: str,
    tool_name: str,
    args: list[Any] = None,
    kwargs: dict[str, Any] = None,
) -> dict[str, Any]:
    """
    Call a tool on a registered agent.

    Args:
        agent_name: Name of the agent to call
        tool_name: Name of the tool to execute
        args: Positional arguments for the tool (optional)
        kwargs: Keyword arguments for the tool (optional)

    Returns:
        Dict containing call result or error information
    """
    try:
        engine = get_engine()
        args = args or []
        kwargs = kwargs or {}

        result = engine.call_agent_tool(agent_name, tool_name, args, kwargs)
        logger.debug(f"Tool call successful: {agent_name}.{tool_name}")
        return result
    except ValueError as e:
        logger.warning(f"Tool call validation error: {e}")
        raise
    except RuntimeError as e:
        logger.error(f"Tool call runtime error: {e}")
        raise
    except ConnectionError as e:
        logger.error(f"Tool call connection error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during tool call: {e}")
        raise


def get_registered_agents() -> dict[str, str]:
    """
    Get all currently registered agents.

    Returns:
        Dict mapping agent names to their addresses
    """
    try:
        engine = get_engine()
        agents = engine.get_registered_agents()
        logger.debug(f"Retrieved {len(agents)} registered agents")
        return agents
    except Exception as e:
        logger.error(f"Failed to get registered agents: {e}")
        raise


def is_agent_registered(agent_name: str) -> bool:
    """
    Check if an agent is currently registered.

    Args:
        agent_name: Name of the agent to check

    Returns:
        True if agent is registered, False otherwise
    """
    try:
        engine = get_engine()
        return engine.is_agent_registered(agent_name)
    except Exception as e:
        logger.error(f"Failed to check agent registration for {agent_name}: {e}")
        raise


def get_circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """
    Get the current circuit breaker status for all agents.

    Returns:
        Dict mapping agent names to their circuit breaker state
    """
    try:
        engine = get_engine()
        status = engine.get_circuit_breaker_status()
        logger.debug(f"Circuit breaker status retrieved for {len(status)} agents")
        return status
    except Exception as e:
        logger.error(f"Failed to get circuit breaker status: {e}")
        raise


def get_bus_health() -> dict[str, Any]:
    """
    Get comprehensive health status of the MCP Bus.

    Returns:
        Dict containing health information
    """
    try:
        engine = get_engine()
        health = engine.get_health_status()
        logger.debug("MCP Bus health check completed")
        return health
    except Exception as e:
        logger.error(f"Failed to get MCP Bus health: {e}")
        raise


def get_bus_stats() -> dict[str, Any]:
    """
    Get statistics about MCP Bus operations.

    Returns:
        Dict containing operational statistics
    """
    try:
        engine = get_engine()
        stats = engine.get_stats()
        logger.debug("MCP Bus statistics retrieved")
        return stats
    except Exception as e:
        logger.error(f"Failed to get MCP Bus statistics: {e}")
        raise


def notify_gpu_orchestrator() -> bool:
    """
    Notify the GPU Orchestrator that MCP Bus is ready.

    Returns:
        True if notification succeeded, False otherwise
    """
    try:
        engine = get_engine()
        success = engine.notify_gpu_orchestrator()
        if success:
            logger.info("GPU Orchestrator notification successful")
        else:
            logger.warning("GPU Orchestrator notification failed")
        return success
    except Exception as e:
        logger.error(f"Failed to notify GPU Orchestrator: {e}")
        return False


def health_check() -> dict[str, Any]:
    """
    Perform a comprehensive health check of the MCP Bus.

    Returns:
        Dict containing health check results
    """
    try:
        engine = get_engine()
        health_status = engine.get_health_status()
        stats = engine.get_stats()

        # Build agent components from engine-provided agent_details (best-effort)
        agent_details = health_status.get("agent_details", [])
        agents_component = {
            "status": "healthy",
            "registered_agents": len(engine.agents),
            "details": agent_details,
        }
        # Determine agent component status
        for a in agent_details:
            if a.get("status") not in ("healthy", "unknown"):
                agents_component["status"] = "degraded"
                break

        # Check for critical issues
        issues = []
        if health_status.get("circuit_breaker_active", False):
            issues.append("Circuit breaker is active for one or more agents")

        if len(engine.agents) == 0:
            issues.append("No agents currently registered")

        if agents_component.get("status") == "degraded":
            issues.append("One or more registered agents reported unhealthy or unreachable")

        result = {
            "timestamp": time.time(),
            "overall_status": health_status.get("status", "degraded"),
            "components": {
                "agent_registry": {
                    "status": "healthy" if len(engine.agents) > 0 else "degraded",
                    "registered_agents": len(engine.agents),
                },
                "agents": agents_component,
                "circuit_breaker": {
                    "status": "healthy"
                    if not health_status.get("circuit_breaker_active")
                    else "degraded",
                    "active_breakers": stats.get("open_circuits", 0),
                },
                "communication": {
                    "status": "healthy",
                    "total_failures": stats.get("total_circuit_breaker_failures", 0),
                },
            },
            "issues": issues,
            "stats": stats,
        }

        # Emit metrics for overall and per-agent health (best-effort)
        try:
            from common.metrics import JustNewsMetrics

            m = JustNewsMetrics("mcp_bus")
            # overall
            m.set_health_status(result.get("overall_status", "unknown"), target="overall", agent="mcp_bus")
            # per-agent
            for a in agent_details:
                status = a.get("status", "unknown")
                m.set_health_status(status, target="per_agent", agent=a.get("agent"))
        except Exception:
            logger.debug("Prometheus metrics not emitted for MCP Bus health (optional)")

        logger.debug(f"Health check completed: {result['overall_status']}")
        return result

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "timestamp": time.time(),
            "overall_status": "unhealthy",
            "components": {},
            "issues": [f"Health check error: {str(e)}"],
            "error": str(e),
        }
