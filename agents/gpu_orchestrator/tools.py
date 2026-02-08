"""
GPU Orchestrator Tools - Utility functions for GPU management.

This module provides high-level utility functions that delegate to the
GPUOrchestratorEngine for GPU monitoring, leasing, model preloading, and
other orchestration tasks.
"""

from typing import Any

from .gpu_orchestrator_engine import engine


def get_gpu_info() -> dict[str, Any]:
    """Get comprehensive GPU information including telemetry and MPS status."""
    return engine.get_comprehensive_gpu_info()


def get_policy() -> dict[str, Any]:
    """Get current GPU allocation policy."""
    return engine.get_policy()


def set_policy(
    max_memory_per_agent_mb: int | None = None,
    allow_fractional_shares: bool | None = None,
    kill_on_oom: bool | None = None,
) -> dict[str, Any]:
    """Update GPU allocation policy."""
    update = {}
    if max_memory_per_agent_mb is not None:
        update["max_memory_per_agent_mb"] = max_memory_per_agent_mb
    if allow_fractional_shares is not None:
        update["allow_fractional_shares"] = allow_fractional_shares
    if kill_on_oom is not None:
        update["kill_on_oom"] = kill_on_oom
    return engine.update_policy(update)


def get_allocations() -> dict[str, Any]:
    """Get current GPU lease allocations."""
    return engine.get_allocations()


def lease_gpu(agent: str, min_memory_mb: int | None = 0) -> dict[str, Any]:
    """Obtain a GPU lease for an agent."""
    return engine.lease_gpu(agent, min_memory_mb)


def release_gpu_lease(token: str) -> dict[str, Any]:
    """Release a GPU lease by token."""
    return engine.release_gpu_lease(token)


def models_preload(
    agents: list[str] | None = None, refresh: bool = False, strict: bool | None = None
) -> dict[str, Any]:
    """Start model preload job."""
    return engine.start_model_preload(agents, refresh, strict)


def models_status() -> dict[str, Any]:
    """Get model preload status."""
    return engine.get_model_preload_status()


def get_mps_allocation() -> dict[str, Any]:
    """Get MPS allocation configuration."""
    return engine.get_mps_allocation_config()


def get_metrics() -> str:
    """Get Prometheus metrics as text."""
    return engine.get_metrics_text()
