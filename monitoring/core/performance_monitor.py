"""
Performance Monitor for JustNews

Real-time performance monitoring, bottleneck detection, and alerting.
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import psutil
from prometheus_client import Gauge

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from monitoring.core.metrics_collector import (
    Alert,
    AlertSeverity,
    EnhancedMetricsCollector,
    get_enhanced_metrics_collector,
)

logger = logging.getLogger(__name__)


class PerformanceMetric(Enum):
    """Performance metrics to monitor"""

    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_IO = "disk_io"
    NETWORK_IO = "network_io"
    GPU_USAGE = "gpu_usage"
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    QUEUE_SIZE = "queue_size"
    ERROR_RATE = "error_rate"


class BottleneckType(Enum):
    """Types of performance bottlenecks"""

    CPU_BOUND = "cpu_bound"
    MEMORY_BOUND = "memory_bound"
    IO_BOUND = "io_bound"
    NETWORK_BOUND = "network_bound"
    GPU_BOUND = "gpu_bound"
    CONTENTION = "contention"
    THROUGHPUT_LIMITED = "throughput_limited"


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration"""

    metric: PerformanceMetric
    warning_threshold: float
    critical_threshold: float
    duration_seconds: int = 300  # 5 minutes
    cooldown_seconds: int = 600  # 10 minutes


@dataclass
class PerformanceSnapshot:
    """Snapshot of system performance"""

    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_read_bytes: int
    disk_write_bytes: int
    network_sent_bytes: int
    network_recv_bytes: int
    gpu_memory_percent: float | None = None
    gpu_utilization_percent: float | None = None
    active_threads: int = 0
    open_files: int = 0


@dataclass
class BottleneckAnalysis:
    """Analysis of performance bottlenecks"""

    timestamp: datetime
    primary_bottleneck: BottleneckType
    severity: str
    confidence_score: float
    recommendations: list[str]
    affected_components: list[str]
    metrics_snapshot: PerformanceSnapshot


class PerformanceMonitor:
    """
    Real-time performance monitoring and bottleneck detection.

    Monitors system resources, application performance, and detects
    bottlenecks with automated alerting and recommendations.
    """

    def __init__(self, agent_name: str, collector: EnhancedMetricsCollector):
        self.agent_name = agent_name
        self.collector = collector
        self.registry = collector.registry

        # Performance monitoring metrics
        self.performance_score = Gauge(
            "justnews_performance_score",
            "Overall performance score (0-100)",
            ["agent", "component"],
            registry=self.registry,
        )

        self.bottleneck_detected = Gauge(
            "justnews_bottleneck_detected",
            "Bottleneck detection flag (1=detection, 0=normal)",
            ["agent", "bottleneck_type"],
            registry=self.registry,
        )

        self.resource_contention = Gauge(
            "justnews_resource_contention_percent",
            "Resource contention percentage",
            ["agent", "resource_type"],
            registry=self.registry,
        )

        # Performance thresholds
        self._thresholds: dict[PerformanceMetric, PerformanceThreshold] = (
            self._get_default_thresholds()
        )

        # Monitoring state
        self._snapshots: list[PerformanceSnapshot] = []
        self._bottleneck_history: list[BottleneckAnalysis] = []
        self._alert_cooldowns: dict[str, datetime] = {}

        # Background monitoring
        self._monitoring_task: asyncio.Task | None = None
        self._analysis_task: asyncio.Task | None = None

        # Performance baselines
        self._baselines: dict[PerformanceMetric, float] = {}
        self._baseline_samples: dict[PerformanceMetric, list[float]] = {}

        logger.info(f"Initialized performance monitor for agent: {agent_name}")

    def _get_default_thresholds(self) -> dict[PerformanceMetric, PerformanceThreshold]:
        """Get default performance thresholds"""
        return {
            PerformanceMetric.CPU_USAGE: PerformanceThreshold(
                metric=PerformanceMetric.CPU_USAGE,
                warning_threshold=70.0,
                critical_threshold=90.0,
            ),
            PerformanceMetric.MEMORY_USAGE: PerformanceThreshold(
                metric=PerformanceMetric.MEMORY_USAGE,
                warning_threshold=80.0,
                critical_threshold=95.0,
            ),
            PerformanceMetric.RESPONSE_TIME: PerformanceThreshold(
                metric=PerformanceMetric.RESPONSE_TIME,
                warning_threshold=2.0,  # 2 seconds
                critical_threshold=10.0,  # 10 seconds
            ),
            PerformanceMetric.ERROR_RATE: PerformanceThreshold(
                metric=PerformanceMetric.ERROR_RATE,
                warning_threshold=5.0,  # 5%
                critical_threshold=15.0,  # 15%
            ),
            PerformanceMetric.QUEUE_SIZE: PerformanceThreshold(
                metric=PerformanceMetric.QUEUE_SIZE,
                warning_threshold=100,
                critical_threshold=500,
            ),
        }

    async def start_monitoring(self):
        """Start performance monitoring"""
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        self._analysis_task = asyncio.create_task(self._analysis_loop())

    async def stop_monitoring(self):
        """Stop performance monitoring"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
        if self._analysis_task:
            self._analysis_task.cancel()

        await asyncio.gather(
            self._monitoring_task or asyncio.sleep(0),
            self._analysis_task or asyncio.sleep(0),
            return_exceptions=True,
        )

    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while True:
            try:
                await self._take_performance_snapshot()
                await self._update_performance_metrics()
                await asyncio.sleep(30)  # Monitor every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)

    async def _analysis_loop(self):
        """Background analysis loop"""
        while True:
            try:
                await self._analyze_performance()
                await self._check_thresholds()
                await asyncio.sleep(60)  # Analyze every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in analysis loop: {e}")
                await asyncio.sleep(120)

    async def _take_performance_snapshot(self):
        """Take a performance snapshot"""
        try:
            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            disk_read = disk_io.read_bytes if disk_io else 0
            disk_write = disk_io.write_bytes if disk_io else 0

            # Network I/O
            net_io = psutil.net_io_counters()
            net_sent = net_io.bytes_sent if net_io else 0
            net_recv = net_io.bytes_recv if net_io else 0

            # GPU metrics (if available)
            gpu_memory_percent = None
            gpu_utilization_percent = None

            try:
                import GPUtil

                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]  # Primary GPU
                    gpu_memory_percent = (gpu.memoryUsed / gpu.memoryTotal) * 100
                    gpu_utilization_percent = gpu.load * 100
            except ImportError:
                pass

            # Process-specific metrics
            process = psutil.Process()
            active_threads = process.num_threads()
            open_files = len(process.open_files())

            # Create snapshot
            snapshot = PerformanceSnapshot(
                timestamp=datetime.now(UTC),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                disk_read_bytes=disk_read,
                disk_write_bytes=disk_write,
                network_sent_bytes=net_sent,
                network_recv_bytes=net_recv,
                gpu_memory_percent=gpu_memory_percent,
                gpu_utilization_percent=gpu_utilization_percent,
                active_threads=active_threads,
                open_files=open_files,
            )

            # Store snapshot (keep last 24 hours)
            self._snapshots.append(snapshot)
            cutoff = datetime.now(UTC) - timedelta(hours=24)
            self._snapshots = [s for s in self._snapshots if s.timestamp > cutoff]

        except Exception as e:
            logger.error(f"Error taking performance snapshot: {e}")

    async def _update_performance_metrics(self):
        """Update performance metrics in Prometheus"""
        try:
            if not self._snapshots:
                return

            latest = self._snapshots[-1]

            # Update resource utilization metrics
            self.collector.resource_utilization.labels(
                agent=self.agent_name, resource_type="cpu", resource_name="system"
            ).set(latest.cpu_percent)

            self.collector.resource_utilization.labels(
                agent=self.agent_name, resource_type="memory", resource_name="system"
            ).set(latest.memory_percent)

            if latest.gpu_utilization_percent is not None:
                self.collector.resource_utilization.labels(
                    agent=self.agent_name,
                    resource_type="gpu",
                    resource_name="utilization",
                ).set(latest.gpu_utilization_percent)

            if latest.gpu_memory_percent is not None:
                self.collector.resource_utilization.labels(
                    agent=self.agent_name, resource_type="gpu", resource_name="memory"
                ).set(latest.gpu_memory_percent)

            # Calculate performance score
            performance_score = self._calculate_performance_score(latest)
            self.performance_score.labels(
                agent=self.agent_name, component="system"
            ).set(performance_score)

        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")

    def _calculate_performance_score(self, snapshot: PerformanceSnapshot) -> float:
        """Calculate overall performance score (0-100)"""
        score = 100.0

        # CPU impact
        if snapshot.cpu_percent > 90:
            score -= 30
        elif snapshot.cpu_percent > 70:
            score -= 15

        # Memory impact
        if snapshot.memory_percent > 95:
            score -= 30
        elif snapshot.memory_percent > 80:
            score -= 15

        # GPU impact (if available)
        if snapshot.gpu_utilization_percent and snapshot.gpu_utilization_percent > 90:
            score -= 20
        elif snapshot.gpu_utilization_percent and snapshot.gpu_utilization_percent > 70:
            score -= 10

        return max(0.0, score)

    async def _analyze_performance(self):
        """Analyze performance data for bottlenecks"""
        try:
            if len(self._snapshots) < 5:  # Need minimum samples
                return

            # Analyze recent snapshots (last 10 minutes)
            recent_snapshots = [
                s
                for s in self._snapshots
                if s.timestamp > datetime.now(UTC) - timedelta(minutes=10)
            ]

            if len(recent_snapshots) < 3:
                return

            # Detect bottlenecks
            bottleneck = await self._detect_bottleneck(recent_snapshots)

            if bottleneck:
                # Reset bottleneck indicators
                for bottleneck_type in BottleneckType:
                    self.bottleneck_detected.labels(
                        agent=self.agent_name, bottleneck_type=bottleneck_type.value
                    ).set(0)

                # Set detected bottleneck
                self.bottleneck_detected.labels(
                    agent=self.agent_name,
                    bottleneck_type=bottleneck.primary_bottleneck.value,
                ).set(1)

                # Store analysis
                self._bottleneck_history.append(bottleneck)

                # Keep only recent history
                cutoff = datetime.now(UTC) - timedelta(hours=24)
                self._bottleneck_history = [
                    b for b in self._bottleneck_history if b.timestamp > cutoff
                ]

                # Trigger alert if severe
                if bottleneck.severity in ["high", "critical"]:
                    await self._trigger_bottleneck_alert(bottleneck)

        except Exception as e:
            logger.error(f"Error analyzing performance: {e}")

    async def _detect_bottleneck(
        self, snapshots: list[PerformanceSnapshot]
    ) -> BottleneckAnalysis | None:
        """Detect performance bottlenecks from snapshots"""
        if not snapshots:
            return None

        latest = snapshots[-1]

        # Calculate averages
        avg_cpu = sum(s.cpu_percent for s in snapshots) / len(snapshots)
        avg_memory = sum(s.memory_percent for s in snapshots) / len(snapshots)

        # Simple bottleneck detection logic
        bottlenecks = []

        # CPU bottleneck
        if avg_cpu > 85:
            bottlenecks.append((BottleneckType.CPU_BOUND, 0.9, "high"))
        elif avg_cpu > 70:
            bottlenecks.append((BottleneckType.CPU_BOUND, 0.7, "medium"))

        # Memory bottleneck
        if avg_memory > 90:
            bottlenecks.append((BottleneckType.MEMORY_BOUND, 0.9, "high"))
        elif avg_memory > 75:
            bottlenecks.append((BottleneckType.MEMORY_BOUND, 0.7, "medium"))

        # GPU bottleneck (if available)
        if latest.gpu_utilization_percent and latest.gpu_utilization_percent > 85:
            bottlenecks.append((BottleneckType.GPU_BOUND, 0.8, "high"))
        elif latest.gpu_utilization_percent and latest.gpu_utilization_percent > 70:
            bottlenecks.append((BottleneckType.GPU_BOUND, 0.6, "medium"))

        if not bottlenecks:
            return None

        # Select primary bottleneck (highest confidence)
        primary_bottleneck, confidence, severity = max(bottlenecks, key=lambda x: x[1])

        # Generate recommendations
        recommendations = self._generate_recommendations(primary_bottleneck, latest)

        return BottleneckAnalysis(
            timestamp=datetime.now(UTC),
            primary_bottleneck=primary_bottleneck,
            severity=severity,
            confidence_score=confidence,
            recommendations=recommendations,
            affected_components=[self.agent_name],
            metrics_snapshot=latest,
        )

    def _generate_recommendations(
        self, bottleneck: BottleneckType, snapshot: PerformanceSnapshot
    ) -> list[str]:
        """Generate recommendations for bottleneck resolution"""
        recommendations = []

        if bottleneck == BottleneckType.CPU_BOUND:
            recommendations.extend(
                [
                    "Consider increasing CPU allocation or optimizing CPU-intensive operations",
                    "Review and optimize algorithms for better CPU efficiency",
                    "Consider horizontal scaling if CPU usage remains high",
                ]
            )

        elif bottleneck == BottleneckType.MEMORY_BOUND:
            recommendations.extend(
                [
                    "Increase memory allocation or optimize memory usage",
                    "Implement memory pooling or object reuse patterns",
                    "Review data structures for memory efficiency",
                    "Consider implementing memory limits and cleanup routines",
                ]
            )

        elif bottleneck == BottleneckType.GPU_BOUND:
            recommendations.extend(
                [
                    "Optimize GPU kernel operations and memory transfers",
                    "Consider GPU memory optimization techniques",
                    "Review batch sizes and GPU utilization patterns",
                ]
            )

        elif bottleneck == BottleneckType.IO_BOUND:
            recommendations.extend(
                [
                    "Optimize disk I/O operations and implement caching",
                    "Consider SSD storage for improved I/O performance",
                    "Implement asynchronous I/O operations where possible",
                ]
            )

        return recommendations

    async def _check_thresholds(self):
        """Check performance thresholds and trigger alerts"""
        try:
            if not self._snapshots:
                return

            latest = self._snapshots[-1]

            # Check each threshold
            for metric, threshold in self._thresholds.items():
                current_value = self._get_metric_value(metric, latest)

                if current_value is None:
                    continue

                alert_key = f"{metric.value}_{threshold.critical_threshold}"

                # Check cooldown
                if alert_key in self._alert_cooldowns:
                    if datetime.now(UTC) < self._alert_cooldowns[alert_key]:
                        continue  # Still in cooldown
                    else:
                        del self._alert_cooldowns[alert_key]

                # Check if threshold exceeded
                if current_value > threshold.critical_threshold:
                    severity = AlertSeverity.CRITICAL
                    threshold_value = threshold.critical_threshold
                elif current_value > threshold.warning_threshold:
                    severity = AlertSeverity.WARNING
                    threshold_value = threshold.warning_threshold
                else:
                    continue

                # Trigger alert
                await self._trigger_threshold_alert(
                    metric, current_value, threshold_value, severity
                )

                # Set cooldown
                self._alert_cooldowns[alert_key] = datetime.now(UTC) + timedelta(
                    seconds=threshold.cooldown_seconds
                )

        except Exception as e:
            logger.error(f"Error checking thresholds: {e}")

    def _get_metric_value(
        self, metric: PerformanceMetric, snapshot: PerformanceSnapshot
    ) -> float | None:
        """Get metric value from snapshot"""
        if metric == PerformanceMetric.CPU_USAGE:
            return snapshot.cpu_percent
        elif metric == PerformanceMetric.MEMORY_USAGE:
            return snapshot.memory_percent
        elif metric == PerformanceMetric.GPU_USAGE:
            return snapshot.gpu_utilization_percent
        else:
            return None

    async def _trigger_bottleneck_alert(self, bottleneck: BottleneckAnalysis):
        """Trigger bottleneck alert"""
        alert = Alert(
            rule_name=f"bottleneck_{bottleneck.primary_bottleneck.value}",
            severity=AlertSeverity.WARNING
            if bottleneck.severity == "medium"
            else AlertSeverity.CRITICAL,
            message=f"Performance bottleneck detected: {bottleneck.primary_bottleneck.value.replace('_', ' ').title()}",
            value=bottleneck.confidence_score * 100,  # Convert to percentage
            threshold=70.0,  # 70% confidence threshold
            timestamp=bottleneck.timestamp,
            labels={
                "bottleneck_type": bottleneck.primary_bottleneck.value,
                "severity": bottleneck.severity,
                "agent": self.agent_name,
            },
        )

        await self.collector._handle_alert(alert)

    async def _trigger_threshold_alert(
        self,
        metric: PerformanceMetric,
        current_value: float,
        threshold: float,
        severity: AlertSeverity,
    ):
        """Trigger threshold alert"""
        alert = Alert(
            rule_name=f"threshold_{metric.value}",
            severity=severity,
            message=f"Performance threshold exceeded: {metric.value} = {current_value:.2f} (threshold: {threshold:.2f})",
            value=current_value,
            threshold=threshold,
            timestamp=datetime.now(UTC),
            labels={"metric": metric.value, "agent": self.agent_name},
        )

        await self.collector._handle_alert(alert)

    def get_performance_report(self, hours: int = 1) -> dict[str, Any]:
        """Get performance report for the last N hours"""
        cutoff = datetime.now(UTC) - timedelta(hours=hours)

        recent_snapshots = [s for s in self._snapshots if s.timestamp > cutoff]

        if not recent_snapshots:
            return {"status": "no_data", "hours": hours}

        # Calculate statistics
        cpu_stats = self._calculate_stats([s.cpu_percent for s in recent_snapshots])
        memory_stats = self._calculate_stats(
            [s.memory_percent for s in recent_snapshots]
        )

        latest = recent_snapshots[-1]

        # Get active bottlenecks
        active_bottlenecks = []
        for bottleneck in self._bottleneck_history[-10:]:  # Last 10 analyses
            if bottleneck.timestamp > cutoff:
                active_bottlenecks.append(
                    {
                        "type": bottleneck.primary_bottleneck.value,
                        "severity": bottleneck.severity,
                        "confidence": bottleneck.confidence_score,
                        "recommendations": bottleneck.recommendations,
                    }
                )

        return {
            "status": "active",
            "hours": hours,
            "sample_count": len(recent_snapshots),
            "cpu_usage": cpu_stats,
            "memory_usage": memory_stats,
            "current_threads": latest.active_threads,
            "current_open_files": latest.open_files,
            "gpu_available": latest.gpu_utilization_percent is not None,
            "gpu_utilization": latest.gpu_utilization_percent,
            "gpu_memory": latest.gpu_memory_percent,
            "performance_score": self._calculate_performance_score(latest),
            "active_bottlenecks": active_bottlenecks,
            "alerts_active": len(self.collector.get_active_alerts()),
        }

    def _calculate_stats(self, values: list[float]) -> dict[str, float]:
        """Calculate basic statistics for a list of values"""
        if not values:
            return {"min": 0, "max": 0, "avg": 0, "current": 0}

        return {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "current": values[-1],
        }

    def set_threshold(self, metric: PerformanceMetric, threshold: PerformanceThreshold):
        """Set custom threshold for a metric"""
        self._thresholds[metric] = threshold

    def get_recommendations(self) -> list[str]:
        """Get current performance recommendations"""
        recommendations = []

        # Check recent bottlenecks
        recent_bottlenecks = [
            b
            for b in self._bottleneck_history
            if b.timestamp > datetime.now(UTC) - timedelta(hours=1)
        ]

        for bottleneck in recent_bottlenecks[-3:]:  # Last 3 bottlenecks
            recommendations.extend(bottleneck.recommendations)

        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                unique_recommendations.append(rec)
                seen.add(rec)

        return unique_recommendations[:5]  # Top 5 recommendations


# Global performance monitor instances
_performance_monitors: dict[str, PerformanceMonitor] = {}


def get_performance_monitor(agent_name: str) -> PerformanceMonitor:
    """Get or create performance monitor for an agent"""
    if agent_name not in _performance_monitors:
        collector = get_enhanced_metrics_collector(agent_name)
        _performance_monitors[agent_name] = PerformanceMonitor(agent_name, collector)

    return _performance_monitors[agent_name]


def init_performance_monitor_for_agent(agent_name: str) -> PerformanceMonitor:
    """Initialize performance monitor for a specific agent"""
    collector = get_enhanced_metrics_collector(agent_name)
    monitor = PerformanceMonitor(agent_name, collector)
    _performance_monitors[agent_name] = monitor
    return monitor
