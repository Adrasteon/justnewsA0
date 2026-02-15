"""
Analytics Tools for JustNews

Wrapper functions for analytics operations that can be called by other agents
and services in the JustNews system.
"""

import os
from typing import Any

import requests

from common.observability import get_logger

logger = get_logger(__name__)

# Analytics service configuration
ANALYTICS_SERVICE_URL = os.environ.get("ANALYTICS_SERVICE_URL", "http://localhost:8012")
ANALYTICS_SERVICE_TIMEOUT = int(os.environ.get("ANALYTICS_TIMEOUT", "30"))


def get_system_health() -> dict[str, Any] | None:
    """
    Get comprehensive system health metrics.

    Returns:
        Dict containing system health score and metrics, or None if request fails
    """
    try:
        payload = {}
        response = requests.post(
            f"{ANALYTICS_SERVICE_URL}/get_system_health",
            json=payload,
            timeout=ANALYTICS_SERVICE_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                logger.debug("Retrieved system health metrics")
                return data.get("data")
            else:
                logger.warning(f"System health request failed: {data}")
                return None
        else:
            logger.warning(
                f"System health request failed with status {response.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"System health request failed: {e}")
        return None


def get_performance_metrics(hours: int = 1) -> dict[str, Any] | None:
    """
    Get real-time performance metrics for specified time period.

    Args:
        hours: Number of hours to analyze (1-24)

    Returns:
        Dict containing performance analytics data, or None if request fails
    """
    try:
        payload = {"hours": hours}
        response = requests.post(
            f"{ANALYTICS_SERVICE_URL}/get_performance_metrics",
            json=payload,
            timeout=ANALYTICS_SERVICE_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                logger.debug(f"Retrieved performance metrics for {hours} hours")
                return data.get("data")
            else:
                logger.warning(f"Performance metrics request failed: {data}")
                return None
        else:
            logger.warning(
                f"Performance metrics request failed with status {response.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"Performance metrics request failed: {e}")
        return None


def get_agent_profile(agent_name: str, hours: int = 24) -> dict[str, Any] | None:
    """
    Get performance profile for specific agent.

    Args:
        agent_name: Name of the agent to profile
        hours: Number of hours to analyze (1-168)

    Returns:
        Dict containing agent performance profile, or None if request fails
    """
    try:
        payload = {"agent_name": agent_name, "hours": hours}
        response = requests.post(
            f"{ANALYTICS_SERVICE_URL}/get_agent_profile",
            json=payload,
            timeout=ANALYTICS_SERVICE_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                logger.debug(f"Retrieved profile for agent {agent_name}")
                return data.get("data")
            else:
                logger.warning(f"Agent profile request failed: {data}")
                return None
        else:
            logger.warning(
                f"Agent profile request failed with status {response.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"Agent profile request failed: {e}")
        return None


def get_optimization_recommendations(hours: int = 24) -> list[dict[str, Any]] | None:
    """
    Get advanced optimization recommendations.

    Args:
        hours: Number of hours to analyze for recommendations

    Returns:
        List of optimization recommendations, or None if request fails
    """
    try:
        payload = {"hours": hours}
        response = requests.post(
            f"{ANALYTICS_SERVICE_URL}/get_optimization_recommendations",
            json=payload,
            timeout=ANALYTICS_SERVICE_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                recommendations = data.get("data", [])
                logger.debug(
                    f"Retrieved {len(recommendations)} optimization recommendations"
                )
                return recommendations
            else:
                logger.warning(f"Optimization recommendations request failed: {data}")
                return None
        else:
            logger.warning(
                f"Optimization recommendations request failed with status {response.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"Optimization recommendations request failed: {e}")
        return None


def record_performance_metric(metric_data: dict[str, Any]) -> bool:
    """
    Record a custom performance metric.

    Args:
        metric_data: Dictionary containing metric data with required fields:
            - agent_name: Name of the agent
            - operation: Operation being performed
            - processing_time_s: Processing time in seconds
            - batch_size: Batch size used
            - success: Boolean indicating success

    Returns:
        True if metric recorded successfully, False otherwise
    """
    try:
        response = requests.post(
            f"{ANALYTICS_SERVICE_URL}/record_performance_metric",
            json=metric_data,
            timeout=ANALYTICS_SERVICE_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                logger.debug(
                    f"Recorded performance metric for {metric_data.get('agent_name')}"
                )
                return True
            else:
                logger.warning(f"Metric recording failed: {data}")
                return False
        else:
            logger.warning(
                f"Metric recording failed with status {response.status_code}"
            )
            return False

    except Exception as e:
        logger.error(f"Metric recording request failed: {e}")
        return False


def check_analytics_service_health() -> dict[str, Any]:
    """
    Check the health status of the analytics service.

    Returns:
        Dict containing health status information
    """
    try:
        response = requests.get(f"{ANALYTICS_SERVICE_URL}/health", timeout=10)

        if response.status_code == 200:
            return {
                "status": "healthy",
                "service": "analytics",
                "response_time": response.elapsed.total_seconds(),
                "details": response.json(),
            }
        else:
            return {
                "status": "unhealthy",
                "service": "analytics",
                "error": f"HTTP {response.status_code}",
                "details": response.text,
            }

    except Exception as e:
        return {"status": "error", "service": "analytics", "error": str(e)}


def get_analytics_dashboard_url() -> str:
    """
    Get the URL for the analytics dashboard web interface.

    Returns:
        String containing the dashboard URL
    """
    return f"{ANALYTICS_SERVICE_URL}/dashboard"


def export_analytics_report(hours: int = 24) -> dict[str, Any] | None:
    """
    Export comprehensive analytics report.

    Args:
        hours: Number of hours to include in the report

    Returns:
        Dict containing complete analytics report, or None if request fails

    Note: This is an admin/advanced function that may not be exposed via MCP
    """
    try:
        # This would typically be an internal/admin endpoint
        # For now, we'll construct it as a direct call
        payload = {"hours": hours}

        # Note: This endpoint might not exist in the current implementation
        # It's included for future extensibility
        response = requests.post(
            f"{ANALYTICS_SERVICE_URL}/export_report",
            json=payload,
            timeout=ANALYTICS_SERVICE_TIMEOUT * 2,  # Longer timeout for reports
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                logger.info(f"Exported analytics report for {hours} hours")
                return data.get("data")
            else:
                logger.warning(f"Report export failed: {data}")
                return None
        else:
            logger.warning(f"Report export failed with status {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Report export request failed: {e}")
        return None


def get_analytics_service_info() -> dict[str, Any] | None:
    """
    Get information about the analytics service capabilities.

    Returns:
        Dict containing service information, or None if request fails
    """
    try:
        response = requests.get(
            f"{ANALYTICS_SERVICE_URL}/info", timeout=ANALYTICS_SERVICE_TIMEOUT
        )

        if response.status_code == 200:
            return response.json()
        else:
            logger.warning(
                f"Service info request failed with status {response.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"Service info request failed: {e}")
        return None
