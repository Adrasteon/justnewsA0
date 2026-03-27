"""
Enhanced Metrics Collection Framework for JustNews

Extends the basic Prometheus integration with advanced business metrics,
performance monitoring, anomaly detection, and real-time alerting.
"""

import asyncio
import logging
import statistics
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import psutil
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

from common.metrics import JustNewsMetrics

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics collected"""

    BUSINESS = "business"
    PERFORMANCE = "performance"
    SYSTEM = "system"
    QUALITY = "quality"
    SECURITY = "security"
    COMPLIANCE = "compliance"


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MetricThreshold:
    """Threshold configuration for alerting"""

    warning_threshold: float
    critical_threshold: float
    direction: str = "above"  # "above", "below", or "outside"
    baseline_window_minutes: int = 60
    cooldown_minutes: int = 5


@dataclass
class AlertRule:
    """Alert rule configuration"""

    name: str
    metric_name: str
    thresholds: MetricThreshold
    description: str
    severity: AlertSeverity
    enabled: bool = True
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """Alert instance"""

    rule_name: str
    severity: AlertSeverity
    message: str
    value: float
    threshold: float
    timestamp: datetime
    labels: dict[str, str] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: datetime | None = None


class EnhancedMetricsCollector:
    """
    Enhanced metrics collection framework extending JustNewsMetrics.

    Provides advanced business metrics, anomaly detection, alerting,
    and performance monitoring capabilities.
    """

    def __init__(self, agent_name: str, registry: CollectorRegistry | None = None):
        self.agent_name = agent_name
        # Break recursion loop by disabling enhanced metrics in the base metrics that we wrap
        self.base_metrics = JustNewsMetrics(agent_name, registry, enable_enhanced=False)
        self.registry = self.base_metrics.registry

        # Enhanced metrics storage
        self._custom_metrics: dict[str, Any] = {}
        self._metric_history: dict[str, list[tuple[datetime, float]]] = {}
        self._alert_rules: dict[str, AlertRule] = {}
        self._active_alerts: dict[str, Alert] = {}
        self._alert_handlers: list[Callable] = []

        # Anomaly detection
        self._baseline_metrics: dict[str, dict[str, Any]] = {}
        self._anomaly_thresholds: dict[str, float] = {}

        # Performance monitoring
        self._performance_baselines: dict[str, float] = {}
        self._slow_operation_thresholds: dict[str, float] = {}

        # Business metrics
        self._business_metrics: dict[str, Any] = {}

        # Initialize enhanced metrics
        self._init_enhanced_metrics()
        self._init_business_metrics()
        self._init_performance_metrics()
        self._init_security_metrics()

        # Start background tasks
        self._monitoring_task: asyncio.Task | None = None
        self._alerting_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None

        logger.info(f"Initialized enhanced metrics collector for agent: {agent_name}")

    def _init_enhanced_metrics(self):
        """Initialize enhanced Prometheus metrics"""
        # Business metrics
        self.content_processed_total = Counter(
            "justnews_content_processed_total",
            "Total content items processed",
            ["agent", "content_type", "processing_stage"],
            registry=self.registry,
        )

        self.content_quality_score = Histogram(
            "justnews_content_quality_score",
            "Content quality score distribution",
            ["agent", "content_type", "quality_metric"],
            buckets=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            registry=self.registry,
        )

        # Performance metrics
        self.operation_latency = Histogram(
            "justnews_operation_latency_seconds",
            "Operation latency in seconds",
            ["agent", "operation_type", "operation_category"],
            buckets=[0.001, 0.01, 0.1, 1.0, 5.0, 10.0, 30.0],
            registry=self.registry,
        )

        self.throughput_rate = Gauge(
            "justnews_throughput_rate_per_second",
            "Operations per second",
            ["agent", "operation_type"],
            registry=self.registry,
        )

        # System health metrics
        self.health_score = Gauge(
            "justnews_health_score",
            "Overall health score (0-100)",
            ["agent", "health_component"],
            registry=self.registry,
        )

        self.error_rate = Gauge(
            "justnews_error_rate_percentage",
            "Error rate as percentage",
            ["agent", "error_category"],
            registry=self.registry,
        )

        # Resource utilization
        self.resource_utilization = Gauge(
            "justnews_resource_utilization_percent",
            "Resource utilization percentage",
            ["agent", "resource_type", "resource_name"],
            registry=self.registry,
        )

    def _init_business_metrics(self):
        """Initialize business-specific metrics"""
        # Content processing metrics
        self.articles_processed = Counter(
            "justnews_articles_processed_total",
            "Total articles processed",
            ["agent", "source_type", "processing_result"],
            registry=self.registry,
        )

        self.fact_checks_performed = Counter(
            "justnews_fact_checks_total",
            "Total fact checks performed",
            ["agent", "check_type", "result"],
            registry=self.registry,
        )

        self.sentiment_analysis_count = Counter(
            "justnews_sentiment_analysis_total",
            "Total sentiment analyses performed",
            ["agent", "sentiment_type", "confidence_level"],
            registry=self.registry,
        )

        # Quality metrics
        self.content_accuracy_score = Histogram(
            "justnews_content_accuracy_score",
            "Content accuracy score distribution",
            ["agent", "verification_method"],
            buckets=[0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0],
            registry=self.registry,
        )

        self.bias_detection_score = Histogram(
            "justnews_bias_detection_score",
            "Bias detection confidence score",
            ["agent", "bias_type"],
            buckets=[0.0, 0.3, 0.5, 0.7, 0.9, 1.0],
            registry=self.registry,
        )

    def _init_performance_metrics(self):
        """Initialize advanced performance metrics"""
        # Memory and GC metrics
        self.memory_pressure = Gauge(
            "justnews_memory_pressure_percent",
            "Memory pressure percentage",
            ["agent", "memory_pool"],
            registry=self.registry,
        )

        self.gc_collections_total = Counter(
            "justnews_gc_collections_total",
            "Total garbage collections",
            ["agent", "generation"],
            registry=self.registry,
        )

        # Threading metrics
        self.active_threads = Gauge(
            "justnews_active_threads",
            "Number of active threads",
            ["agent", "thread_pool"],
            registry=self.registry,
        )

        self.thread_queue_size = Gauge(
            "justnews_thread_queue_size",
            "Thread pool queue size",
            ["agent", "thread_pool"],
            registry=self.registry,
        )

        # I/O metrics
        self.io_operations_total = Counter(
            "justnews_io_operations_total",
            "Total I/O operations",
            ["agent", "io_type", "operation"],
            registry=self.registry,
        )

        self.io_latency = Histogram(
            "justnews_io_latency_seconds",
            "I/O operation latency",
            ["agent", "io_type", "operation"],
            buckets=[0.001, 0.01, 0.1, 1.0, 5.0],
            registry=self.registry,
        )

    def _init_security_metrics(self):
        """Initialize security and compliance metrics"""
        # Authentication metrics
        self.auth_attempts_total = Counter(
            "justnews_auth_attempts_total",
            "Total authentication attempts",
            ["agent", "auth_method", "result"],
            registry=self.registry,
        )

        self.auth_failures_total = Counter(
            "justnews_auth_failures_total",
            "Total authentication failures",
            ["agent", "auth_method", "failure_reason"],
            registry=self.registry,
        )

        # Access control metrics
        self.access_denied_total = Counter(
            "justnews_access_denied_total",
            "Total access denied events",
            ["agent", "resource_type", "reason"],
            registry=self.registry,
        )

        # Data protection metrics
        self.data_encryption_operations = Counter(
            "justnews_data_encryption_operations_total",
            "Total data encryption/decryption operations",
            ["agent", "operation_type", "data_type"],
            registry=self.registry,
        )

        # Compliance metrics
        self.compliance_checks_total = Counter(
            "justnews_compliance_checks_total",
            "Total compliance checks performed",
            ["agent", "compliance_type", "result"],
            registry=self.registry,
        )

    async def start_monitoring(self):
        """Start background monitoring tasks"""
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        self._alerting_task = asyncio.create_task(self._alerting_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_monitoring(self):
        """Stop background monitoring tasks"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
        if self._alerting_task:
            self._alerting_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()

        await asyncio.gather(
            self._monitoring_task or asyncio.sleep(0),
            self._alerting_task or asyncio.sleep(0),
            self._cleanup_task or asyncio.sleep(0),
            return_exceptions=True,
        )

    async def _monitoring_loop(self):
        """Background monitoring loop"""
        while True:
            try:
                await self._update_system_metrics()
                await self._update_performance_metrics()
                await self._check_anomalies()
                await asyncio.sleep(30)  # Update every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def _alerting_loop(self):
        """Background alerting loop"""
        while True:
            try:
                await self._evaluate_alert_rules()
                await asyncio.sleep(60)  # Check alerts every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in alerting loop: {e}")
                await asyncio.sleep(120)  # Wait longer on error

    async def _cleanup_loop(self):
        """Background cleanup loop"""
        while True:
            try:
                await self._cleanup_old_data()
                await asyncio.sleep(3600)  # Clean up every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(3600)

    async def _update_system_metrics(self):
        """Update enhanced system metrics"""
        try:
            # Update base system metrics
            self.base_metrics.update_system_metrics()

            # Enhanced memory metrics
            process = psutil.Process()
            memory_info = process.memory_info()

            # Memory pressure calculation
            total_memory = psutil.virtual_memory().total
            memory_pressure = (memory_info.rss / total_memory) * 100

            self.memory_pressure.labels(
                agent=self.agent_name, memory_pool="process"
            ).set(memory_pressure)

            # CPU utilization by core
            cpu_percents = psutil.cpu_percent(percpu=True, interval=1)
            for i, cpu_percent in enumerate(cpu_percents):
                self.resource_utilization.labels(
                    agent=self.agent_name,
                    resource_type="cpu",
                    resource_name=f"core_{i}",
                ).set(cpu_percent)

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.resource_utilization.labels(
                    agent=self.agent_name,
                    resource_type="disk",
                    resource_name="read_bytes",
                ).set(disk_io.read_bytes)

                self.resource_utilization.labels(
                    agent=self.agent_name,
                    resource_type="disk",
                    resource_name="write_bytes",
                ).set(disk_io.write_bytes)

            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io:
                self.resource_utilization.labels(
                    agent=self.agent_name,
                    resource_type="network",
                    resource_name="bytes_sent",
                ).set(net_io.bytes_sent)

                self.resource_utilization.labels(
                    agent=self.agent_name,
                    resource_type="network",
                    resource_name="bytes_recv",
                ).set(net_io.bytes_recv)

        except Exception as e:
            logger.error(f"Error updating system metrics: {e}")

    async def _update_performance_metrics(self):
        """Update performance metrics"""
        try:
            # Threading metrics
            self.active_threads.labels(agent=self.agent_name, thread_pool="main").set(
                threading.active_count()
            )

            # GC metrics (if available)
            try:
                import gc

                for i, count in enumerate(gc.get_count()):
                    self.gc_collections_total.labels(
                        agent=self.agent_name, generation=str(i)
                    ).inc(count)
            except ImportError:
                pass

        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")

    async def _check_anomalies(self):
        """Check for metric anomalies"""
        try:
            for metric_name, history in self._metric_history.items():
                if len(history) < 10:  # Need minimum samples
                    continue

                # Calculate recent average and standard deviation
                recent_values = [value for _, value in history[-20:]]  # Last 20 samples
                if len(recent_values) < 5:
                    continue

                avg = statistics.mean(recent_values)
                std_dev = (
                    statistics.stdev(recent_values) if len(recent_values) > 1 else 0
                )

                # Check for anomalies (3 sigma rule)
                threshold = self._anomaly_thresholds.get(metric_name, 3.0)
                current_value = recent_values[-1]

                if std_dev > 0 and abs(current_value - avg) > (threshold * std_dev):
                    await self._trigger_anomaly_alert(
                        metric_name, current_value, avg, std_dev
                    )

        except Exception as e:
            logger.error(f"Error checking anomalies: {e}")

    async def _evaluate_alert_rules(self):
        """Evaluate alert rules against current metrics"""
        try:
            for _rule_name, rule in self._alert_rules.items():
                if not rule.enabled:
                    continue

                # Get current metric value (this would need to be implemented
                # based on how metrics are stored and accessed)
                current_value = await self._get_metric_value(rule.metric_name)

                if current_value is None:
                    continue

                # Check thresholds
                thresholds = rule.thresholds
                alert_triggered = False

                if thresholds.direction == "above":
                    if current_value > thresholds.critical_threshold:
                        alert_triggered = True
                        severity = AlertSeverity.CRITICAL
                        threshold = thresholds.critical_threshold
                    elif current_value > thresholds.warning_threshold:
                        alert_triggered = True
                        severity = AlertSeverity.WARNING
                        threshold = thresholds.warning_threshold

                elif thresholds.direction == "below":
                    if current_value < thresholds.critical_threshold:
                        alert_triggered = True
                        severity = AlertSeverity.CRITICAL
                        threshold = thresholds.critical_threshold
                    elif current_value < thresholds.warning_threshold:
                        alert_triggered = True
                        severity = AlertSeverity.WARNING
                        threshold = thresholds.warning_threshold

                if alert_triggered:
                    await self._trigger_alert(rule, severity, current_value, threshold)

        except Exception as e:
            logger.error(f"Error evaluating alert rules: {e}")

    async def _trigger_anomaly_alert(
        self, metric_name: str, current_value: float, avg: float, std_dev: float
    ):
        """Trigger an anomaly alert"""
        alert = Alert(
            rule_name=f"anomaly_{metric_name}",
            severity=AlertSeverity.WARNING,
            message=f"Anomaly detected in {metric_name}: {current_value:.2f} "
            f"(avg: {avg:.2f}, std_dev: {std_dev:.2f})",
            value=current_value,
            threshold=avg + (3 * std_dev),
            timestamp=datetime.now(UTC),
            labels={"metric": metric_name, "type": "anomaly"},
        )

        await self._handle_alert(alert)

    async def _trigger_alert(
        self,
        rule: AlertRule,
        severity: AlertSeverity,
        current_value: float,
        threshold: float,
    ):
        """Trigger a configured alert"""
        alert_key = f"{rule.name}_{severity.value}"

        # Check if alert is already active
        if alert_key in self._active_alerts:
            return  # Alert already active

        alert = Alert(
            rule_name=rule.name,
            severity=severity,
            message=rule.description,
            value=current_value,
            threshold=threshold,
            timestamp=datetime.now(UTC),
            labels=rule.labels,
        )

        self._active_alerts[alert_key] = alert
        await self._handle_alert(alert)

    async def _handle_alert(self, alert: Alert):
        """Handle alert by calling registered handlers"""
        for handler in self._alert_handlers:
            try:
                await handler(alert)
            except Exception as e:
                logger.error(f"Error in alert handler: {e}")

    async def _get_metric_value(self, metric_name: str) -> float | None:
        """Get current value of a metric"""
        # This would need to be implemented to retrieve metric values
        # from the Prometheus registry or internal storage
        return None

    async def _cleanup_old_data(self):
        """Clean up old metric history and resolved alerts"""
        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=24)

            # Clean up old metric history
            for metric_name in self._metric_history:
                self._metric_history[metric_name] = [
                    (timestamp, value)
                    for timestamp, value in self._metric_history[metric_name]
                    if timestamp > cutoff_time
                ]

            # Clean up old resolved alerts
            resolved_alerts = [
                alert_key
                for alert_key, alert in self._active_alerts.items()
                if alert.resolved
                and alert.resolved_at
                and alert.resolved_at < cutoff_time
            ]

            for alert_key in resolved_alerts:
                del self._active_alerts[alert_key]

        except Exception as e:
            logger.error(f"Error in cleanup: {e}")

    # Public API methods

    def record_business_metric(
        self, metric_type: str, value: float, labels: dict[str, str] = None
    ):
        """Record a business metric"""
        labels = labels or {}

        # Store in history for anomaly detection
        if metric_type not in self._metric_history:
            self._metric_history[metric_type] = []

        self._metric_history[metric_type].append((datetime.now(UTC), value))

        # Keep only recent history
        cutoff_time = datetime.now(UTC) - timedelta(hours=24)
        self._metric_history[metric_type] = [
            (ts, val)
            for ts, val in self._metric_history[metric_type]
            if ts > cutoff_time
        ]

        # Update Prometheus metrics based on type
        if metric_type == "content_processed":
            self.content_processed_total.labels(
                agent=self.agent_name,
                content_type=labels.get("content_type", "unknown"),
                processing_stage=labels.get("stage", "unknown"),
            ).inc()

        elif metric_type == "content_quality":
            self.content_quality_score.labels(
                agent=self.agent_name,
                content_type=labels.get("content_type", "unknown"),
                quality_metric=labels.get("metric", "unknown"),
            ).observe(value)

        elif metric_type == "articles_processed":
            self.articles_processed.labels(
                agent=self.agent_name,
                source_type=labels.get("source_type", "unknown"),
                processing_result=labels.get("result", "unknown"),
            ).inc()

    def record_performance_metric(
        self, operation_type: str, duration: float, category: str = "general"
    ):
        """Record a performance metric"""
        self.operation_latency.labels(
            agent=self.agent_name,
            operation_type=operation_type,
            operation_category=category,
        ).observe(duration)

        # Update throughput (simple moving average)
        if operation_type not in self._performance_baselines:
            self._performance_baselines[operation_type] = duration
        else:
            # Exponential moving average
            alpha = 0.1
            self._performance_baselines[operation_type] = (
                alpha * duration
                + (1 - alpha) * self._performance_baselines[operation_type]
            )

    def add_alert_rule(self, rule: AlertRule):
        """Add an alert rule"""
        self._alert_rules[rule.name] = rule

    def remove_alert_rule(self, rule_name: str):
        """Remove an alert rule"""
        if rule_name in self._alert_rules:
            del self._alert_rules[rule_name]

    def add_alert_handler(self, handler: Callable):
        """Add an alert handler"""
        self._alert_handlers.append(handler)

    def remove_alert_handler(self, handler: Callable):
        """Remove an alert handler"""
        if handler in self._alert_handlers:
            self._alert_handlers.remove(handler)

    def get_active_alerts(self) -> list[Alert]:
        """Get list of active alerts"""
        return list(self._active_alerts.values())

    def resolve_alert(self, alert_key: str):
        """Resolve an active alert"""
        if alert_key in self._active_alerts:
            self._active_alerts[alert_key].resolved = True
            self._active_alerts[alert_key].resolved_at = datetime.now(UTC)

    def get_health_score(self) -> float:
        """Calculate overall health score"""
        # Simple health score calculation based on error rates and performance
        error_rate = 0.0  # Would need to calculate from metrics
        performance_score = 100.0  # Would need to calculate from baselines

        health_score = 100.0 - (error_rate * 50.0) - ((100.0 - performance_score) * 0.5)
        return max(0.0, min(100.0, health_score))

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get comprehensive metrics summary"""
        return {
            "agent": self.agent_name,
            "health_score": self.get_health_score(),
            "active_alerts": len(self._active_alerts),
            "total_metrics": len(self._custom_metrics),
            "alert_rules": len(self._alert_rules),
            "performance_baselines": len(self._performance_baselines),
            "timestamp": datetime.now(UTC).isoformat(),
        }


# Global enhanced metrics instance
_enhanced_metrics_instances: dict[str, EnhancedMetricsCollector] = {}


def get_enhanced_metrics_collector(agent_name: str) -> EnhancedMetricsCollector:
    """Get or create enhanced metrics collector for an agent"""
    if agent_name not in _enhanced_metrics_instances:
        _enhanced_metrics_instances[agent_name] = EnhancedMetricsCollector(agent_name)

    return _enhanced_metrics_instances[agent_name]


def init_enhanced_metrics_for_agent(agent_name: str) -> EnhancedMetricsCollector:
    """Initialize enhanced metrics for a specific agent"""
    collector = EnhancedMetricsCollector(agent_name)
    _enhanced_metrics_instances[agent_name] = collector
    return collector
