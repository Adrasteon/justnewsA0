"""JustNews Metrics Library - Prometheus Integration."""

from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from functools import wraps

import psutil
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

try:  # Optional dependency - GPU metrics degrade gracefully when absent.
    import GPUtil  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - depends on environment tooling.
    GPUtil = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class JustNewsMetrics:
    """
    Core metrics collection class for JustNews agents.
    Provides standardized metrics, middleware, and utilities.
    """

    # Agent display names for clearer labeling
    AGENT_DISPLAY_NAMES = {
        # "scout": "content-discovery-agent", (Deprecated)
        # "crawler": "content-discovery-agent", (Duplicated)
        "analyst": "sentiment-analysis-agent",
        "synthesizer": "content-synthesis-agent",
        "fact_checker": "fact-verification-agent",
        "critic": "quality-assessment-agent",
        "memory": "data-storage-agent",
        "reasoning": "logical-reasoning-agent",
        "newsreader": "news-processing-agent",
        "archive": "content-archiving-agent",
        "dashboard": "web-dashboard-agent",
        "analytics": "system-analytics-agent",
        "chief_editor": "workflow-orchestration-agent",
        "crawler": "content-crawling-agent",
        "crawler_scheduler": "content-crawl-scheduler",
        "gpu_orchestrator": "gpu-resource-orchestrator",
        "mcp_bus": "communication-bus",
    }

    # Endpoint display names for clearer labeling
    ENDPOINT_DISPLAY_NAMES = {
        "/health": "health-check-endpoint",
        "/ready": "readiness-check-endpoint",
        "/metrics": "prometheus-metrics-endpoint",
        "/": "root-endpoint",
        "/unified_production_crawl": "crawling-operation-endpoint",
        "/get_crawler_info": "crawler-info-endpoint",
        "/get_performance_metrics": "performance-metrics-endpoint",
        "/analyze": "sentiment-analysis-endpoint",
        "/synthesize": "content-synthesis-endpoint",
        "/fact_check": "fact-checking-endpoint",
        "/quality_check": "quality-assessment-endpoint",
        "/store": "data-storage-endpoint",
        "/retrieve": "data-retrieval-endpoint",
        "/reason": "logical-reasoning-endpoint",
        "/process": "content-processing-endpoint",
        "/balance": "load-balancing-endpoint",
        "/archive": "content-archiving-endpoint",
        "/dashboard": "dashboard-endpoint",
        "/analytics": "analytics-endpoint",
        "/orchestrate": "workflow-orchestration-endpoint",
        "/gpu_status": "gpu-status-endpoint",
        "/register": "agent-registration-endpoint",
        "/call": "inter-agent-communication-endpoint",
    }

    # HTTP status code mappings
    STATUS_DISPLAY_NAMES = {
        "200": "success",
        "201": "created",
        "400": "bad-request",
        "401": "unauthorized",
        "403": "forbidden",
        "404": "not-found",
        "500": "internal-server-error",
        "502": "bad-gateway",
        "503": "service-unavailable",
    }

    def __init__(
        self,
        agent_name: str,
        registry: CollectorRegistry | None = None,
        enable_enhanced: bool = True,
    ):
        """
        Initialize metrics for an agent.

        Args:
            agent_name: Name of the agent (e.g., 'scout', 'analyst')
            registry: Optional custom registry (useful for testing)
            enable_enhanced: Whether to attempt initializing the enhanced metrics collector (default: True)
        """
        self.agent_name = agent_name
        self.display_name = self.AGENT_DISPLAY_NAMES.get(
            agent_name, f"{agent_name}-agent"
        )
        self.registry = registry or CollectorRegistry()

        # Initialize Core Monitoring Enhanced Collector if available
        # But skip if explicitly disabled (to avoid recursion when EnhancedMetricsCollector
        # initializes its own JustNewsMetrics instance)
        if enable_enhanced:
            try:
                from monitoring.core.metrics_collector import (
                    get_enhanced_metrics_collector,
                )

                # We don't replace self yet to maintain backward compatibility,
                # but we ensure the enhanced collector is initialized.
                self._enhanced_collector = get_enhanced_metrics_collector(agent_name)
            except ImportError:
                self._enhanced_collector = None
        else:
            self._enhanced_collector = None

        self._init_standard_metrics()
        self._init_agent_specific_metrics()
        self._init_system_metrics()

        # Lazy metric registries for backwards-compatibility helper methods.
        self._custom_counters: dict[str, Counter] = {}
        self._custom_histograms: dict[str, Histogram] = {}
        self._custom_gauges: dict[str, Gauge] = {}

        logger.info(
            "Initialized metrics for agent: %s (display: %s)",
            agent_name,
            self.display_name,
        )

        # Initialize gauges with default values to ensure series existence
        self._initialize_gauge_defaults()

    def _initialize_gauge_defaults(self):
        """Initialize gauges with default values (0) so they appear in Grafana immediately."""
        try:
            # Initialize Active Connections
            self.active_connections.labels(
                agent=self.agent_name,
                agent_display_name=self.display_name
            ).set(0)

            # Initialize Queue Size (Main)
            self.processing_queue_size.labels(
                agent=self.agent_name,
                agent_display_name=self.display_name,
                queue_type="main",
                queue_display_name="Main Queue"
            ).set(0)

            # Initialize Health (Healthy by default)
            self.agent_health_status.labels(
                agent=self.agent_name,
                agent_display_name=self.display_name,
                target="overall"
            ).set(0) # 0 = Healthy
        except Exception as e:
            logger.warning("Failed to initialize default metrics for %s: %s", self.agent_name, e)

    def _init_standard_metrics(self):
        """Initialize standard HTTP and request metrics."""
        # Request metrics with enhanced labels
        self.requests_total = Counter(
            "justnews_requests_total",
            "Total number of requests processed",
            [
                "agent",
                "agent_display_name",
                "method",
                "endpoint",
                "endpoint_display_name",
                "status",
                "status_display_name",
            ],
            registry=self.registry,
        )

        self.request_duration = Histogram(
            "justnews_request_duration_seconds",
            "Request duration in seconds",
            [
                "agent",
                "agent_display_name",
                "method",
                "endpoint",
                "endpoint_display_name",
            ],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
            registry=self.registry,
        )

        # Error metrics with enhanced labels
        self.errors_total = Counter(
            "justnews_errors_total",
            "Total number of errors",
            [
                "agent",
                "agent_display_name",
                "error_type",
                "endpoint",
                "endpoint_display_name",
            ],
            registry=self.registry,
        )

        # Active connections with enhanced labels
        self.active_connections = Gauge(
            "justnews_active_connections",
            "Number of active connections",
            ["agent", "agent_display_name"],
            registry=self.registry,
        )

    def _init_agent_specific_metrics(self):
        """Initialize agent-specific metrics (to be extended by subclasses)."""
        # Processing metrics with enhanced labels
        self.processing_queue_size = Gauge(
            "justnews_processing_queue_size",
            "Current size of processing queue",
            ["agent", "agent_display_name", "queue_type", "queue_display_name"],
            registry=self.registry,
        )

        self.processing_duration = Histogram(
            "justnews_processing_duration_seconds",
            "Processing duration in seconds",
            ["agent", "agent_display_name", "operation_type", "operation_display_name"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
            registry=self.registry,
        )

        # Quality metrics with enhanced labels
        self.quality_score = Histogram(
            "justnews_quality_score",
            "Quality score distribution",
            ["agent", "agent_display_name", "metric_type", "metric_display_name"],
            buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=self.registry,
        )

        # Agent & bus health metric (0=healthy,1=degraded,2=unhealthy,3=unreachable,4=unknown)
        self.agent_health_status = Gauge(
            "justnews_agent_health_status",
            "Health status of agents and overall bus (0=healthy,1=degraded,2=unhealthy,3=unreachable,4=unknown)",
            ["agent", "agent_display_name", "target"],
            registry=self.registry,
        )

    def set_health_status(self, status: str, target: str = "overall", agent: str | None = None, response_time: float | None = None) -> None:
        """Set health status for an agent or the overall bus.

        Args:
            status: Human readable status ('healthy', 'degraded', 'unhealthy', 'unreachable', 'unknown')
            target: 'overall' or 'per_agent'
            agent: Agent name (for per-agent targets). If None, defaults to this metrics' agent.
            response_time: Optional probe response time (not stored, but preserved for possible future use)
        """
        mapping = {
            "healthy": 0,
            "degraded": 1,
            "unhealthy": 2,
            "unreachable": 3,
            "unknown": 4,
        }

        value = mapping.get(status, 4)
        agent_label = agent or self.agent_name

        try:
            self.agent_health_status.labels(
                agent=agent_label, agent_display_name=self.display_name, target=target
            ).set(value)
        except Exception as e:
            logger.debug("Failed to set health metric: %s", e)


    def _init_system_metrics(self):
        """Initialize system-level metrics."""
        # Memory usage with enhanced labels
        self.memory_usage_bytes = Gauge(
            "justnews_memory_usage_bytes",
            "Memory usage in bytes",
            ["agent", "agent_display_name", "type", "memory_type_display_name"],
            registry=self.registry,
        )

        # CPU usage with enhanced labels
        self.cpu_usage_percent = Gauge(
            "justnews_cpu_usage_percent",
            "CPU usage percentage",
            ["agent", "agent_display_name"],
            registry=self.registry,
        )

        if GPUtil is None:
            logger.info("GPUtil not available; GPU metrics disabled")
            self.gpu_memory_used_bytes = None
            self.gpu_utilization_percent = None
            return

        try:
            gpu_count = len(GPUtil.getGPUs())
            if gpu_count > 0:
                self.gpu_memory_used_bytes = Gauge(
                    "justnews_gpu_memory_used_bytes",
                    "GPU memory used in bytes",
                    ["agent", "agent_display_name", "gpu_id", "gpu_display_name"],
                    registry=self.registry,
                )

                self.gpu_utilization_percent = Gauge(
                    "justnews_gpu_utilization_percent",
                    "GPU utilization percentage",
                    ["agent", "agent_display_name", "gpu_id", "gpu_display_name"],
                    registry=self.registry,
                )
            else:
                self.gpu_memory_used_bytes = None
                self.gpu_utilization_percent = None
        except Exception as exc:  # pragma: no cover - depends on GPU availability.
            logger.warning("Could not initialize GPU metrics: %s", exc)
            self.gpu_memory_used_bytes = None
            self.gpu_utilization_percent = None

    def record_request(self, method: str, endpoint: str, status: int, duration: float):
        """Record an HTTP request."""
        endpoint_display = self.ENDPOINT_DISPLAY_NAMES.get(
            endpoint, f"{endpoint.replace('/', '').replace('_', '-')}-endpoint"
        )
        status_display = self.STATUS_DISPLAY_NAMES.get(str(status), f"http-{status}")

        self.requests_total.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            method=method,
            endpoint=endpoint,
            endpoint_display_name=endpoint_display,
            status=str(status),
            status_display_name=status_display,
        ).inc()

        self.request_duration.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            method=method,
            endpoint=endpoint,
            endpoint_display_name=endpoint_display,
        ).observe(duration)

    def record_error(self, error_type: str, endpoint: str = ""):
        """Record an error."""
        endpoint_display = self.ENDPOINT_DISPLAY_NAMES.get(
            endpoint,
            f"{endpoint.replace('/', '').replace('_', '-')}-endpoint"
            if endpoint
            else "unknown-endpoint",
        )

        self.errors_total.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            error_type=error_type,
            endpoint=endpoint,
            endpoint_display_name=endpoint_display,
        ).inc()

    def record_processing(self, operation_type: str, duration: float):
        """Record processing operation."""
        # Create a more readable operation display name
        operation_display = operation_type.replace("_", "-").replace(" ", "-")

        self.processing_duration.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            operation_type=operation_type,
            operation_display_name=operation_display,
        ).observe(duration)

    def update_queue_size(self, queue_type: str, size: int):
        """Update processing queue size."""
        queue_display = queue_type.replace("_", "-").replace(" ", "-")

        self.processing_queue_size.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            queue_type=queue_type,
            queue_display_name=queue_display,
        ).set(size)

    def record_quality_score(self, metric_type: str, score: float):
        """Record quality score."""
        metric_display = metric_type.replace("_", "-").replace(" ", "-")

        self.quality_score.labels(
            agent=self.agent_name,
            agent_display_name=self.display_name,
            metric_type=metric_type,
            metric_display_name=metric_display,
        ).observe(score)

    def update_system_metrics(self):
        """Update system resource metrics."""
        try:
            # Memory metrics
            process = psutil.Process()
            memory_info = process.memory_info()

            self.memory_usage_bytes.labels(
                agent=self.agent_name,
                agent_display_name=self.display_name,
                type="rss",
                memory_type_display_name="resident-set-size",
            ).set(memory_info.rss)

            self.memory_usage_bytes.labels(
                agent=self.agent_name,
                agent_display_name=self.display_name,
                type="vms",
                memory_type_display_name="virtual-memory-size",
            ).set(memory_info.vms)

            # CPU metrics
            cpu_percent = process.cpu_percent(interval=1.0)
            self.cpu_usage_percent.labels(
                agent=self.agent_name, agent_display_name=self.display_name
            ).set(cpu_percent)

            if GPUtil and self.gpu_memory_used_bytes and self.gpu_utilization_percent:
                try:
                    gpus = GPUtil.getGPUs()
                    for i, gpu in enumerate(gpus):
                        gpu_display = f"gpu-{i}"

                        self.gpu_memory_used_bytes.labels(
                            agent=self.agent_name,
                            agent_display_name=self.display_name,
                            gpu_id=str(i),
                            gpu_display_name=gpu_display,
                        ).set(gpu.memoryUsed * 1024 * 1024)  # Convert MB to bytes

                        self.gpu_utilization_percent.labels(
                            agent=self.agent_name,
                            agent_display_name=self.display_name,
                            gpu_id=str(i),
                            gpu_display_name=gpu_display,
                        ).set(gpu.load * 100)
                except (
                    Exception
                ) as exc:  # pragma: no cover - GPU availability dependent.
                    logger.debug("Could not update GPU metrics: %s", exc)

        except Exception as e:
            logger.warning(f"Could not update system metrics: {e}")

    def get_metrics(self) -> str:
        """Get metrics in Prometheus format."""
        return generate_latest(self.registry).decode("utf-8")

    # ------------------------------------------------------------------
    # Compatibility helpers (legacy code expects generic metric helpers)
    # ------------------------------------------------------------------
    def increment(self, metric_name: str, amount: float = 1.0) -> None:
        """Increment a counter metric by ``amount``."""
        counter = self._get_or_create_counter(metric_name)
        counter.labels(agent=self.agent_name, agent_display_name=self.display_name).inc(
            amount
        )

    def timing(self, metric_name: str, value: float) -> None:
        """Record a timing value via a histogram."""
        histogram = self._get_or_create_histogram(metric_name)
        histogram.labels(
            agent=self.agent_name, agent_display_name=self.display_name
        ).observe(value)

    def gauge(self, metric_name: str, value: float) -> None:
        """Set a gauge metric to ``value``."""
        gauge = self._get_or_create_gauge(metric_name)
        gauge.labels(agent=self.agent_name, agent_display_name=self.display_name).set(
            value
        )

    @contextmanager
    def measure_time(self, operation_type: str):
        """Context manager to measure operation duration."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.record_processing(operation_type, duration)

    async def request_middleware(self, request, call_next):
        """
        FastAPI middleware for automatic request metrics collection.

        Usage:
            app.middleware("http")(metrics.request_middleware)
        """
        start_time = time.time()

        # Update active connections
        self.active_connections.labels(
            agent=self.agent_name, agent_display_name=self.display_name
        ).inc()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Record successful request
            self.record_request(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
                duration=duration,
            )

            return response

        except Exception as e:
            duration = time.time() - start_time

            # Record error
            self.record_error(error_type=type(e).__name__, endpoint=request.url.path)

            # Record failed request
            self.record_request(
                method=request.method,
                endpoint=request.url.path,
                status=500,
                duration=duration,
            )

            raise

        finally:
            # Decrement active connections
            self.active_connections.labels(
                agent=self.agent_name, agent_display_name=self.display_name
            ).dec()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _sanitize_metric_key(self, name: str) -> str:
        """Normalize metric names to Prometheus-safe keys."""
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        return sanitized.lower().strip("_") or "metric"

    def _get_or_create_counter(self, metric_name: str) -> Counter:
        key = self._sanitize_metric_key(metric_name)
        if key not in self._custom_counters:
            self._custom_counters[key] = Counter(
                f"justnews_custom_counter_{key}",
                f"Custom counter metric for {metric_name}",
                ["agent", "agent_display_name"],
                registry=self.registry,
            )
        return self._custom_counters[key]

    def _get_or_create_histogram(self, metric_name: str) -> Histogram:
        key = self._sanitize_metric_key(metric_name)
        if key not in self._custom_histograms:
            self._custom_histograms[key] = Histogram(
                f"justnews_custom_histogram_{key}",
                f"Custom histogram metric for {metric_name}",
                ["agent", "agent_display_name"],
                registry=self.registry,
            )
        return self._custom_histograms[key]

    def _get_or_create_gauge(self, metric_name: str) -> Gauge:
        key = self._sanitize_metric_key(metric_name)
        if key not in self._custom_gauges:
            self._custom_gauges[key] = Gauge(
                f"justnews_custom_gauge_{key}",
                f"Custom gauge metric for {metric_name}",
                ["agent", "agent_display_name"],
                registry=self.registry,
            )
        return self._custom_gauges[key]


# Global metrics instance (can be overridden per agent)
_default_metrics = None


def get_metrics(agent_name: str) -> JustNewsMetrics:
    """Get or create metrics instance for an agent."""
    global _default_metrics

    if _default_metrics is None or _default_metrics.agent_name != agent_name:
        _default_metrics = JustNewsMetrics(agent_name)

    return _default_metrics


def init_metrics_for_agent(agent_name: str) -> JustNewsMetrics:
    """Initialize metrics for a specific agent."""
    return JustNewsMetrics(agent_name)


# Utility functions for common patterns
def measure_processing_time(operation_type: str):
    """Decorator to measure processing time."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            agent_name = (
                getattr(args[0], "agent_name", "unknown") if args else "unknown"
            )
            metrics = get_metrics(agent_name)

            with metrics.measure_time(operation_type):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def record_quality_metric(metric_type: str, score: float, agent_name: str = None):
    """Record a quality metric."""
    if agent_name is None:
        # Try to infer from context
        agent_name = "unknown"

    metrics = get_metrics(agent_name)
    metrics.record_quality_score(metric_type, score)


def update_system_metrics(agent_name: str = None):
    """Update system metrics for an agent."""
    if agent_name is None:
        agent_name = "unknown"

    metrics = get_metrics(agent_name)
    metrics.update_system_metrics()
