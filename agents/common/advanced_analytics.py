"""
Advanced Performance Analytics Engine for JustNews

Provides comprehensive performance monitoring, trend analysis, bottleneck detection,
and optimization recommendations for the multi-agent GPU system.

Features:
- Real-time performance metrics aggregation
- Historical trend analysis and forecasting
- Automated bottleneck detection
- Resource optimization recommendations
- Performance profiling per agent
- System health monitoring
- Custom analytics queries
"""

import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common.observability import get_logger

# Configure logging

logger = get_logger(__name__)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics data structure"""

    timestamp: datetime
    agent_name: str
    operation: str
    processing_time_s: float
    batch_size: int
    success: bool
    gpu_memory_allocated_mb: float
    gpu_memory_reserved_mb: float
    gpu_utilization_pct: float
    temperature_c: float
    power_draw_w: float
    throughput_items_per_s: float


@dataclass
class AnalyticsSummary:
    """Analytics summary with trends and insights"""

    time_range_hours: int
    total_operations: int
    avg_processing_time_s: float
    avg_throughput_items_per_s: float
    success_rate_pct: float
    peak_gpu_memory_mb: float
    avg_gpu_utilization_pct: float
    bottleneck_indicators: list[str]
    optimization_recommendations: list[str]
    performance_trends: dict[str, Any]


class AdvancedAnalyticsEngine:
    """
    Advanced performance analytics engine with real-time monitoring,
    trend analysis, and optimization recommendations.
    """

    def __init__(self, max_history_hours: int = 24, analysis_interval_s: int = 60):
        self.max_history_hours = max_history_hours
        self.analysis_interval_s = analysis_interval_s

        # Data storage
        self.metrics_buffer = deque(
            maxlen=10000
        )  # Recent metrics for real-time analysis
        self.historical_data = defaultdict(list)  # Agent-specific historical data
        self.performance_trends = {}
        self.bottleneck_history = deque(maxlen=100)

        # Analysis state
        self.last_analysis_time = datetime.now()
        self.system_health_score = 100.0
        self.optimization_recommendations = []

        # Threading
        self.analysis_thread = None
        self.running = False
        self.lock = threading.Lock()

        # Configuration
        self.data_dir = Path(__file__).parent.parent.parent / "logs" / "analytics"
        self.data_dir.mkdir(exist_ok=True)

        logger.info("🚀 Advanced Analytics Engine initialized")

    def start(self):
        """Start the analytics engine"""
        if self.running:
            return

        self.running = True
        self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self.analysis_thread.start()
        logger.info("📊 Analytics engine started")

    def stop(self):
        """Stop the analytics engine"""
        self.running = False
        if self.analysis_thread:
            self.analysis_thread.join(timeout=5)
        logger.info("🛑 Analytics engine stopped")

    def record_metric(self, metric: PerformanceMetrics):
        """Record a performance metric"""
        with self.lock:
            self.metrics_buffer.append(metric)

            # Store in historical data
            agent_key = f"{metric.agent_name}_{metric.operation}"
            self.historical_data[agent_key].append(asdict(metric))

            # Keep only recent history
            cutoff_time = datetime.now() - timedelta(hours=self.max_history_hours)
            self.historical_data[agent_key] = [
                m
                for m in self.historical_data[agent_key]
                if isinstance(m["timestamp"], str)
                and datetime.fromisoformat(m["timestamp"]) > cutoff_time
                or isinstance(m["timestamp"], datetime)
                and m["timestamp"] > cutoff_time
            ]

    def get_real_time_analytics(self, hours: int = 1) -> AnalyticsSummary:
        """Get real-time analytics summary"""
        with self.lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_metrics = [
                m for m in self.metrics_buffer if m.timestamp > cutoff_time
            ]

            if not recent_metrics:
                return AnalyticsSummary(
                    time_range_hours=hours,
                    total_operations=0,
                    avg_processing_time_s=0.0,
                    avg_throughput_items_per_s=0.0,
                    success_rate_pct=0.0,
                    peak_gpu_memory_mb=0.0,
                    avg_gpu_utilization_pct=0.0,
                    bottleneck_indicators=[],
                    optimization_recommendations=[],
                    performance_trends={},
                )

            # Calculate metrics
            total_ops = len(recent_metrics)
            successful_ops = len([m for m in recent_metrics if m.success])
            success_rate = (successful_ops / total_ops) * 100 if total_ops > 0 else 0

            avg_processing_time = np.mean([m.processing_time_s for m in recent_metrics])
            avg_throughput = np.mean([m.throughput_items_per_s for m in recent_metrics])
            peak_memory = max([m.gpu_memory_allocated_mb for m in recent_metrics])
            avg_utilization = np.mean(
                [
                    m.gpu_utilization_pct
                    for m in recent_metrics
                    if m.gpu_utilization_pct is not None
                ]
            )

            # Detect bottlenecks
            bottlenecks = self._detect_bottlenecks(recent_metrics)

            # Generate recommendations
            recommendations = self._generate_recommendations(
                recent_metrics, bottlenecks
            )

            # Calculate trends
            trends = self._calculate_trends(recent_metrics)

            return AnalyticsSummary(
                time_range_hours=hours,
                total_operations=total_ops,
                avg_processing_time_s=avg_processing_time,
                avg_throughput_items_per_s=avg_throughput,
                success_rate_pct=success_rate,
                peak_gpu_memory_mb=peak_memory,
                avg_gpu_utilization_pct=avg_utilization,
                bottleneck_indicators=bottlenecks,
                optimization_recommendations=recommendations,
                performance_trends=trends,
            )

    def get_agent_performance_profile(
        self, agent_name: str, hours: int = 24
    ) -> dict[str, Any]:
        """Get detailed performance profile for a specific agent"""
        with self.lock:
            agent_data = []
            for key, metrics in self.historical_data.items():
                if key.startswith(f"{agent_name}_"):
                    cutoff_time = datetime.now() - timedelta(hours=hours)
                    recent_metrics = [
                        m
                        for m in metrics
                        if (
                            isinstance(m["timestamp"], str)
                            and datetime.fromisoformat(m["timestamp"]) > cutoff_time
                        )
                        or (
                            isinstance(m["timestamp"], datetime)
                            and m["timestamp"] > cutoff_time
                        )
                    ]
                    agent_data.extend(recent_metrics)

            if not agent_data:
                return {"error": f"No data found for agent {agent_name}"}

            # Convert to DataFrame for analysis
            df = pd.DataFrame(agent_data)

            # Calculate performance statistics
            profile = {
                "agent_name": agent_name,
                "time_range_hours": hours,
                "total_operations": len(df),
                "operations_breakdown": df["operation"].value_counts().to_dict(),
                "performance_stats": {
                    "avg_processing_time_s": df["processing_time_s"].mean(),
                    "median_processing_time_s": df["processing_time_s"].median(),
                    "p95_processing_time_s": df["processing_time_s"].quantile(0.95),
                    "avg_throughput_items_per_s": df["throughput_items_per_s"].mean(),
                    "success_rate_pct": (df["success"].sum() / len(df)) * 100,
                    "peak_memory_mb": df["gpu_memory_allocated_mb"].max(),
                    "avg_memory_mb": df["gpu_memory_allocated_mb"].mean(),
                },
                "bottlenecks": self._detect_bottlenecks(
                    [PerformanceMetrics(**row) for _, row in df.iterrows()]
                ),
                "recommendations": self._generate_recommendations(
                    [PerformanceMetrics(**row) for _, row in df.iterrows()], []
                ),
            }

            return profile

    def get_system_health_score(self) -> dict[str, Any]:
        """Get overall system health score and status"""
        analytics = self.get_real_time_analytics(hours=1)

        # Calculate health score based on multiple factors
        health_factors = {
            "success_rate": min(100, analytics.success_rate_pct),
            "processing_efficiency": max(
                0, 100 - (analytics.avg_processing_time_s * 10)
            ),  # Lower time = higher score
            "resource_utilization": min(100, analytics.avg_gpu_utilization_pct or 0),
            "memory_efficiency": max(
                0, 100 - (analytics.peak_gpu_memory_mb / 24000) * 100
            ),  # RTX3090 has 24GB
        }

        overall_health = np.mean(list(health_factors.values()))

        # Get advanced optimization recommendations
        try:
            from .advanced_optimization import generate_optimization_recommendations

            optimization_recommendations = generate_optimization_recommendations(
                hours=1
            )
            # Convert to simple list for backward compatibility
            simple_recommendations = [
                rec.title for rec in optimization_recommendations[:5]
            ]
        except Exception:
            simple_recommendations = analytics.optimization_recommendations

        return {
            "overall_health_score": overall_health,
            "health_factors": health_factors,
            "status": "healthy"
            if overall_health >= 80
            else "warning"
            if overall_health >= 60
            else "critical",
            "bottlenecks": analytics.bottleneck_indicators,
            "recommendations": simple_recommendations,
        }

    def _detect_bottlenecks(self, metrics: list[PerformanceMetrics]) -> list[str]:
        """Detect performance bottlenecks"""
        bottlenecks = []

        if not metrics:
            return bottlenecks

        # High processing time bottleneck
        avg_time = np.mean([m.processing_time_s for m in metrics])
        if avg_time > 2.0:  # More than 2 seconds average
            bottlenecks.append(f"High processing time: {avg_time:.2f}s average")

        # Memory pressure bottleneck
        peak_memory = max([m.gpu_memory_allocated_mb for m in metrics])
        if peak_memory > 20000:  # Over 20GB on RTX3090
            bottlenecks.append(f"High memory usage: {peak_memory:.0f}MB peak")

        # Low success rate bottleneck
        success_rate = len([m for m in metrics if m.success]) / len(metrics)
        if success_rate < 0.9:  # Less than 90% success
            bottlenecks.append(f"Low success rate: {success_rate:.1%}")

        # GPU utilization bottleneck
        avg_util = np.mean(
            [
                m.gpu_utilization_pct
                for m in metrics
                if m.gpu_utilization_pct is not None
            ]
        )
        if avg_util and avg_util < 50:  # Less than 50% utilization
            bottlenecks.append(f"Low GPU utilization: {avg_util:.1f}% average")

        return bottlenecks

    def _generate_recommendations(
        self, metrics: list[PerformanceMetrics], bottlenecks: list[str]
    ) -> list[str]:
        """Generate optimization recommendations"""
        recommendations = []

        if not metrics:
            return recommendations

        # Analyze bottlenecks and generate specific recommendations
        for bottleneck in bottlenecks:
            if "processing time" in bottleneck:
                recommendations.append(
                    "Consider increasing batch sizes for better GPU utilization"
                )
                recommendations.append(
                    "Review model quantization settings for faster inference"
                )
            elif "memory usage" in bottleneck:
                recommendations.append("Implement model offloading for large models")
                recommendations.append(
                    "Consider gradient checkpointing to reduce memory footprint"
                )
            elif "success rate" in bottleneck:
                recommendations.append(
                    "Review error handling and implement retry mechanisms"
                )
                recommendations.append("Check model loading and GPU memory allocation")
            elif "GPU utilization" in bottleneck:
                recommendations.append(
                    "Optimize batch sizes for better GPU parallelism"
                )
                recommendations.append(
                    "Consider concurrent processing for I/O bound operations"
                )

        # General recommendations based on metrics
        avg_batch_size = np.mean([m.batch_size for m in metrics])
        if avg_batch_size < 4:
            recommendations.append("Increase batch sizes to improve GPU utilization")

        # Temperature monitoring
        avg_temp = np.mean(
            [m.temperature_c for m in metrics if m.temperature_c is not None]
        )
        if avg_temp and avg_temp > 80:
            recommendations.append(
                "Monitor GPU temperature - consider cooling optimization"
            )

        return list(set(recommendations))  # Remove duplicates

    def _calculate_trends(self, metrics: list[PerformanceMetrics]) -> dict[str, Any]:
        """Calculate performance trends"""
        if len(metrics) < 10:
            return {"insufficient_data": True}

        # Sort by timestamp
        sorted_metrics = sorted(metrics, key=lambda m: m.timestamp)

        # Calculate rolling averages
        times = [m.processing_time_s for m in sorted_metrics]
        throughputs = [m.throughput_items_per_s for m in sorted_metrics]

        trends = {
            "processing_time_trend": "improving"
            if times[-1] < np.mean(times[:-5])
            else "degrading",
            "throughput_trend": "improving"
            if throughputs[-1] > np.mean(throughputs[:-5])
            else "degrading",
            "processing_time_change_pct": (
                (times[-1] - np.mean(times[:-5])) / np.mean(times[:-5])
            )
            * 100,
            "throughput_change_pct": (
                (throughputs[-1] - np.mean(throughputs[:-5]))
                / np.mean(throughputs[:-5])
            )
            * 100,
        }

        return trends

    def _analysis_loop(self):
        """Main analysis loop running in background"""
        while self.running:
            try:
                current_time = datetime.now()

                # Perform analysis every interval
                if (
                    current_time - self.last_analysis_time
                ).seconds >= self.analysis_interval_s:
                    self._perform_periodic_analysis()
                    self.last_analysis_time = current_time

                time.sleep(10)  # Check every 10 seconds

            except Exception as e:
                logger.error(f"Error in analysis loop: {e}")
                time.sleep(30)  # Wait longer on error

    def _perform_periodic_analysis(self):
        """Perform periodic analysis and update recommendations"""
        try:
            # Get recent analytics
            analytics = self.get_real_time_analytics(hours=1)

            # Update system health
            health = self.get_system_health_score()
            self.system_health_score = health["overall_health_score"]

            # Store bottleneck history
            if analytics.bottleneck_indicators:
                self.bottleneck_history.append(
                    {
                        "timestamp": datetime.now(),
                        "bottlenecks": analytics.bottleneck_indicators,
                        "health_score": self.system_health_score,
                    }
                )

            # Update recommendations
            self.optimization_recommendations = analytics.optimization_recommendations

            # Save periodic snapshot
            self._save_periodic_snapshot(analytics)

        except Exception as e:
            logger.error(f"Error in periodic analysis: {e}")

    def _save_periodic_snapshot(self, analytics: AnalyticsSummary):
        """Save periodic analytics snapshot to disk"""
        try:
            snapshot = {
                "timestamp": datetime.now().isoformat(),
                "analytics": asdict(analytics),
                "system_health": self.get_system_health_score(),
            }

            snapshot_file = (
                self.data_dir / f"analytics_snapshot_{int(time.time())}.json"
            )
            with open(snapshot_file, "w") as f:
                json.dump(snapshot, f, indent=2, default=str)

            # Clean up old snapshots (keep last 24 hours)
            cutoff_time = time.time() - (24 * 3600)
            for file in self.data_dir.glob("analytics_snapshot_*.json"):
                if file.stat().st_mtime < cutoff_time:
                    file.unlink()

        except Exception as e:
            logger.error(f"Error saving analytics snapshot: {e}")

    def export_analytics_report(self, hours: int = 24) -> dict[str, Any]:
        """Export comprehensive analytics report"""
        analytics = self.get_real_time_analytics(hours=hours)

        # Get per-agent profiles
        agent_profiles = {}
        for agent_name in [
            "scout",
            "analyst",
            "synthesizer",
            "fact_checker",
            "newsreader",
            "memory",
        ]:
            profile = self.get_agent_performance_profile(agent_name, hours=hours)
            if "error" not in profile:
                agent_profiles[agent_name] = profile

        report = {
            "report_generated_at": datetime.now().isoformat(),
            "time_range_hours": hours,
            "system_overview": asdict(analytics),
            "system_health": self.get_system_health_score(),
            "agent_profiles": agent_profiles,
            "bottleneck_history": list(self.bottleneck_history),
            "recommendations": self.optimization_recommendations,
        }

        return report


# Global analytics engine instance
analytics_engine = AdvancedAnalyticsEngine()


def get_analytics_engine() -> AdvancedAnalyticsEngine:
    """Get the global analytics engine instance"""
    return analytics_engine


def start_analytics_engine():
    """Start the global analytics engine"""
    analytics_engine.start()


def stop_analytics_engine():
    """Stop the global analytics engine"""
    analytics_engine.stop()
