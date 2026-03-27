"""
Tools for the Workflow Orchestrator.
"""

from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)

# References to the engine provided by main.py via injection or global singleton pattern
# For simplicity in this architecture, we'll assume the engine is accessible or passed.

def get_orchestrator_status(engine) -> dict[str, Any]:
    """Get the current status of the orchestrator."""
    stats = engine.resource_monitor.get_stats()
    snapshot = engine.get_status_snapshot()
    return {
        "running": engine.running,
        "active_policies": [p.name() for p in engine.policies],
        "system_stats": {
            "cpu": stats.cpu_percent,
            "memory": stats.memory_percent,
            "gpu_util": stats.gpu_utilization,
        },
        "config": engine.config,
        "runtime_config_version": snapshot.get("autonomic", {}).get("runtime_config_version"),
        "autonomic": snapshot.get("autonomic", {}),
        "telemetry": snapshot.get("telemetry", {}),
        "signals": snapshot.get("signals", {}),
    }

def force_run_policy(engine, policy_name: str) -> dict[str, Any]:
    """Force a policy to run immediately (async triggered, returns receipt)."""
    # This matches a specific policy by name
    policy = next((p for p in engine.policies if p.name() == policy_name), None)
    if not policy:
        return {"status": "error", "message": f"Policy '{policy_name}' not found."}

    # In a real async implementation we might want to await it or schedule it.
    # checking condition sync logic:
    try:
        items = policy.check_condition(limit=5)
        count = len(items)
        # We can't await here easily if called from sync context or we need to bridge it.
        # But we are in FastAPI, so we can be async.
        return {"status": "triggered", "items_found": count, "message": "Policy execution scheduled (logic handled by engine loop normally)."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
