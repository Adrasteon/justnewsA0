"""
Dashboard Tools - Utility functions for JustNews Dashboard

This module provides utility functions that delegate to the dashboard engine,
following the standardized agent structure.
"""

from .dashboard_engine import dashboard_engine


def get_status():
    """Fetch the status of all agents."""
    return dashboard_engine.get_agent_status()


def send_command(call):
    """Send a command to another agent."""
    return dashboard_engine.send_command(call)


def get_gpu_info():
    """Get current GPU information and status."""
    return dashboard_engine.gpu_monitor.get_gpu_info()


def get_gpu_history(hours: int = 1):
    """Get GPU usage history for the specified number of hours."""
    return dashboard_engine.gpu_monitor.get_gpu_history(hours)


def get_agent_gpu_usage():
    """Get GPU usage statistics per agent."""
    return dashboard_engine.gpu_monitor.get_agent_gpu_usage()


def get_gpu_config():
    """Get current GPU configuration from the GPU manager."""
    return dashboard_engine.get_gpu_config()


def update_gpu_config(new_config: dict):
    """Update GPU configuration."""
    return dashboard_engine.update_gpu_config(new_config)


def get_gpu_manager_status():
    """Get comprehensive GPU manager system status."""
    return dashboard_engine.get_gpu_manager_status()


def get_gpu_allocations():
    """Get all current GPU allocations."""
    return dashboard_engine.get_gpu_allocations()


def get_gpu_metrics():
    """Get GPU performance metrics from the manager."""
    return dashboard_engine.get_gpu_metrics()


def get_gpu_history_from_db(
    hours: int = 24, gpu_index: int | None = None, metric: str = "utilization"
):
    """Get GPU metrics history from database."""
    return dashboard_engine.get_gpu_history_from_db(hours, gpu_index, metric)


def get_allocation_history(hours: int = 24, agent_name: str | None = None):
    """Get agent allocation history from database."""
    return dashboard_engine.get_allocation_history(hours, agent_name)


def get_performance_trends(hours: int = 24):
    """Get performance trends data."""
    return dashboard_engine.get_performance_trends(hours)


def get_recent_alerts(limit: int = 50):
    """Get recent alerts from database."""
    return dashboard_engine.get_recent_alerts(limit)


def get_storage_stats():
    """Get database storage statistics."""
    return dashboard_engine.get_storage_stats()


def get_comprehensive_gpu_dashboard_data():
    """Get comprehensive GPU dashboard data including manager integration."""
    return dashboard_engine.get_comprehensive_gpu_dashboard_data()


def ingest_gpu_jsonl(path: str, max_lines: int | None = 10000):
    """Ingest GPU watcher JSONL into dashboard storage."""
    return dashboard_engine.ingest_gpu_jsonl(path, max_lines)
