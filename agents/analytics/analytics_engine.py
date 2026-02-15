"""
Analytics Engine for JustNews

Core business logic for advanced analytics, performance monitoring, and optimization
recommendations. Provides comprehensive system health monitoring and real-time analytics.
"""

import asyncio
import os
from typing import Any

from agents.common.advanced_analytics import (
    get_analytics_engine as get_core_analytics_engine,
)
from agents.common.advanced_analytics import (
    start_analytics_engine,
    stop_analytics_engine,
)
from common.observability import get_logger

logger = get_logger(__name__)


class AnalyticsEngine:
    """
    Analytics engine providing comprehensive performance monitoring, system health tracking,
    and optimization recommendations for the JustNews system.

    This engine wraps the AdvancedAnalyticsEngine and provides agent-specific functionality
    including MCP integration, health monitoring, and dashboard data preparation.
    """

    def __init__(self):
        """Initialize the analytics engine"""
        self._initialized = False
        self._health_status = "initializing"
        self._analytics_engine = None
        self._mcp_bus_url = os.environ.get("MCP_BUS_URL", "http://localhost:8000")
        self._agent_port = int(os.environ.get("ANALYTICS_AGENT_PORT", "8012"))

    async def initialize(self) -> bool:
        """
        Initialize the analytics engine and start background analytics processing.

        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info("📊 Initializing Analytics Engine...")

            # Get the global analytics engine instance
            self._analytics_engine = get_core_analytics_engine()

            # Start the analytics engine if not already running
            start_analytics_engine()

            self._initialized = True
            self._health_status = "healthy"
            logger.info("✅ Analytics Engine initialized successfully")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize Analytics Engine: {e}")
            self._health_status = f"error: {str(e)}"
            return False

    async def shutdown(self) -> None:
        """Shutdown the analytics engine and cleanup resources"""
        try:
            logger.info("📊 Shutting down Analytics Engine...")

            # Stop the analytics engine
            stop_analytics_engine()

            self._initialized = False
            self._health_status = "shutdown"
            logger.info("✅ Analytics Engine shutdown complete")

        except Exception as e:
            logger.error(f"❌ Error during Analytics Engine shutdown: {e}")

    def is_initialized(self) -> bool:
        """Check if the analytics engine is properly initialized"""
        return self._initialized

    async def health_check(self) -> dict[str, Any]:
        """
        Perform comprehensive health check of analytics services.

        Returns:
            Dict containing health status and diagnostic information
        """
        health_info = {
            "service": "analytics_engine",
            "status": self._health_status,
            "initialized": self._initialized,
            "timestamp": asyncio.get_event_loop().time(),
            "checks": {},
        }

        try:
            # Analytics engine health check
            if self._analytics_engine:
                try:
                    system_health = self._analytics_engine.get_system_health_score()
                    health_info["checks"]["analytics_engine"] = {
                        "status": "healthy",
                        "health_score": system_health.get("overall_health_score", 0),
                        "status_message": system_health.get("status", "unknown"),
                    }
                except Exception as e:
                    health_info["checks"]["analytics_engine"] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
                    health_info["status"] = "degraded"
            else:
                health_info["checks"]["analytics_engine"] = {
                    "status": "unhealthy",
                    "error": "Analytics engine not initialized",
                }
                health_info["status"] = "error"

            # MCP Bus connectivity check
            try:
                import requests

                response = requests.get(f"{self._mcp_bus_url}/health", timeout=5)
                if response.status_code == 200:
                    health_info["checks"]["mcp_bus"] = {
                        "status": "healthy",
                        "response_time": response.elapsed.total_seconds(),
                    }
                else:
                    health_info["checks"]["mcp_bus"] = {
                        "status": "unhealthy",
                        "error": f"HTTP {response.status_code}",
                    }
                    health_info["status"] = "degraded"
            except Exception as e:
                health_info["checks"]["mcp_bus"] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                # Don't mark as error if MCP bus is down - analytics can run standalone

            # Overall status determination
            if health_info["status"] == "healthy" and all(
                check.get("status") == "healthy"
                for check in health_info["checks"].values()
                if check.get("status") != "unhealthy"  # Allow MCP bus to be down
            ):
                health_info["status"] = "healthy"
            elif any(
                check.get("status") == "healthy"
                for check in health_info["checks"].values()
            ):
                health_info["status"] = "degraded"
            else:
                health_info["status"] = "error"

        except Exception as e:
            logger.error(f"Health check error: {e}")
            health_info["status"] = "error"
            health_info["error"] = str(e)

        return health_info

    def get_system_health(self) -> dict[str, Any]:
        """
        Get comprehensive system health metrics.

        Returns:
            Dict containing system health score and metrics
        """
        if not self._analytics_engine:
            return {"error": "Analytics engine not initialized"}

        try:
            return self._analytics_engine.get_system_health_score()
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {"error": str(e)}

    def get_performance_metrics(self, hours: int = 1) -> dict[str, Any]:
        """
        Get real-time performance metrics for specified time period.

        Args:
            hours: Number of hours to analyze (1-24)

        Returns:
            Dict containing performance analytics data
        """
        if not self._analytics_engine:
            return {"error": "Analytics engine not initialized"}

        try:
            analytics = self._analytics_engine.get_real_time_analytics(hours=hours)
            return analytics.__dict__
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {"error": str(e)}

    def get_agent_profile(self, agent_name: str, hours: int = 24) -> dict[str, Any]:
        """
        Get performance profile for specific agent.

        Args:
            agent_name: Name of the agent to profile
            hours: Number of hours to analyze (1-168)

        Returns:
            Dict containing agent performance profile
        """
        if not self._analytics_engine:
            return {"error": "Analytics engine not initialized"}

        try:
            return self._analytics_engine.get_agent_performance_profile(
                agent_name, hours=hours
            )
        except Exception as e:
            logger.error(f"Error getting agent profile: {e}")
            return {"error": str(e)}

    def get_optimization_recommendations(self, hours: int = 24) -> list[dict[str, Any]]:
        """
        Get advanced optimization recommendations.

        Args:
            hours: Number of hours to analyze for recommendations

        Returns:
            List of optimization recommendations
        """
        try:
            from agents.common.advanced_optimization import (
                generate_optimization_recommendations,
            )

            recommendations = generate_optimization_recommendations(hours)

            return [
                {
                    "id": rec.id,
                    "category": rec.category.value,
                    "priority": rec.priority.value,
                    "title": rec.title,
                    "description": rec.description,
                    "impact_score": rec.impact_score,
                    "confidence_score": rec.confidence_score,
                    "complexity": rec.implementation_complexity,
                    "time_savings": rec.estimated_time_savings,
                    "affected_agents": rec.affected_agents,
                    "steps": rec.implementation_steps,
                }
                for rec in recommendations
            ]
        except Exception as e:
            logger.error(f"Error getting optimization recommendations: {e}")
            return [{"error": str(e)}]

    def record_performance_metric(self, metric_data: dict[str, Any]) -> bool:
        """
        Record a custom performance metric.

        Args:
            metric_data: Dictionary containing metric data

        Returns:
            bool: True if metric recorded successfully, False otherwise
        """
        if not self._analytics_engine:
            logger.error("Analytics engine not initialized")
            return False

        try:
            from datetime import datetime

            from agents.common.advanced_analytics import PerformanceMetrics

            # Validate required fields
            required_fields = [
                "agent_name",
                "operation",
                "processing_time_s",
                "batch_size",
                "success",
            ]
            for field in required_fields:
                if field not in metric_data:
                    logger.error(f"Missing required field: {field}")
                    return False

            # Create metric object
            metric = PerformanceMetrics(
                timestamp=datetime.now(),
                agent_name=metric_data["agent_name"],
                operation=metric_data["operation"],
                processing_time_s=float(metric_data["processing_time_s"]),
                batch_size=int(metric_data["batch_size"]),
                success=bool(metric_data["success"]),
                gpu_memory_allocated_mb=float(
                    metric_data.get("gpu_memory_allocated_mb", 0.0)
                ),
                gpu_memory_reserved_mb=float(
                    metric_data.get("gpu_memory_reserved_mb", 0.0)
                ),
                gpu_utilization_pct=float(metric_data.get("gpu_utilization_pct", 0.0)),
                temperature_c=float(metric_data.get("temperature_c", 0.0)),
                power_draw_w=float(metric_data.get("power_draw_w", 0.0)),
                throughput_items_per_s=float(
                    metric_data.get("throughput_items_per_s", 0.0)
                ),
            )

            # Record the metric
            self._analytics_engine.record_metric(metric)
            logger.info(f"Recorded performance metric for {metric_data['agent_name']}")
            return True

        except Exception as e:
            logger.error(f"Error recording performance metric: {e}")
            return False

    def export_analytics_report(self, hours: int = 24) -> dict[str, Any]:
        """
        Export comprehensive analytics report.

        Args:
            hours: Number of hours to include in the report

        Returns:
            Dict containing complete analytics report
        """
        if not self._analytics_engine:
            return {"error": "Analytics engine not initialized"}

        try:
            return self._analytics_engine.export_analytics_report(hours=hours)
        except Exception as e:
            logger.error(f"Error exporting analytics report: {e}")
            return {"error": str(e)}

    def get_service_info(self) -> dict[str, Any]:
        """
        Get service information and capabilities.

        Returns:
            Dict containing service metadata and supported features
        """
        return {
            "service": "analytics_engine",
            "version": "1.0.0",
            "description": "Advanced analytics and performance monitoring service for JustNews",
            "features": [
                "Real-time performance monitoring",
                "System health scoring",
                "Agent performance profiling",
                "Bottleneck detection",
                "Optimization recommendations",
                "Historical trend analysis",
                "Interactive dashboard",
                "Comprehensive reporting",
            ],
            "endpoints": [
                "POST /get_system_health",
                "POST /get_performance_metrics",
                "POST /get_agent_profile",
                "POST /get_optimization_recommendations",
                "POST /record_performance_metric",
                "GET /health",
                "GET /ready",
                "GET /dashboard (web interface)",
            ],
            "capabilities": {
                "max_history_hours": 168,  # 1 week
                "analysis_interval_seconds": 60,
                "supported_agents": [
                    "scout",
                    "analyst",
                    "synthesizer",
                    "fact_checker",
                    "newsreader",
                    "memory",
                ],
                "metrics_buffer_size": 10000,
                "bottleneck_history_size": 100,
            },
        }


# Global analytics engine instance
_analytics_engine: AnalyticsEngine | None = None


def get_analytics_engine() -> AnalyticsEngine:
    """Get the global analytics engine instance"""
    global _analytics_engine
    if _analytics_engine is None:
        _analytics_engine = AnalyticsEngine()
    return _analytics_engine


async def initialize_analytics_engine() -> bool:
    """
    Initialize the global analytics engine instance.

    Returns:
        bool: True if initialization successful
    """
    engine = get_analytics_engine()
    return await engine.initialize()


async def shutdown_analytics_engine() -> None:
    """Shutdown the global analytics engine instance"""
    global _analytics_engine
    if _analytics_engine:
        await _analytics_engine.shutdown()
        _analytics_engine = None
