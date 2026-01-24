from __future__ import annotations

"""
JustNews Distributed Tracing System

This module implements comprehensive distributed tracing using OpenTelemetry
for end-to-end request tracing across the multi-agent system.

Key Features:
- OpenTelemetry integration for all agents
- End-to-end request tracing across MCP Bus communications
- Service mesh tracing with Istio integration
- Trace correlation for debugging and optimization
- Performance bottleneck identification
- Distributed transaction monitoring

Author: JustNews Development Team
Date: October 22, 2025
"""

import logging  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from datetime import datetime, timedelta, UTC  # noqa: E402
from typing import Any  # noqa: E402

try:
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.semconv.resource import ResourceAttributes
    from opentelemetry.trace import SpanKind, Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import (
        TraceContextTextMapPropagator,
    )

    _OTEL_AVAILABLE = True
except Exception:
    # OpenTelemetry or dependencies may be missing or incompatible in CI/dev envs.
    # Avoid hard failures at import time — operate in a no-op mode and log warnings when tracing is invoked.
    trace = None
    JaegerExporter = None
    OTLPSpanExporter = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    ResourceAttributes = None
    SpanKind = None
    Status = None
    StatusCode = None
    TraceContextTextMapPropagator = None
    _OTEL_AVAILABLE = False

from config import get_config  # noqa: E402
from common.metrics import JustNewsMetrics  # noqa: E402

logger = logging.getLogger(__name__)

# Global trace provider and tracer
_trace_provider = None
_tracer = None


@dataclass
class TraceContext:
    """Represents a distributed trace context"""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    baggage: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_opentelemetry(cls, span_context: trace.SpanContext) -> TraceContext:
        """Create TraceContext from OpenTelemetry SpanContext"""
        return cls(
            trace_id=hex(span_context.trace_id)[2:],  # Remove 0x prefix
            span_id=hex(span_context.span_id)[2:],  # Remove 0x prefix
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "baggage": self.baggage,
        }


@dataclass
class TraceSpan:
    """Represents a single span in a distributed trace"""

    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    kind: str
    start_time: datetime
    end_time: datetime | None = None
    duration_ms: float | None = None
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    service_name: str = ""
    agent_name: str = ""
    operation: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary for storage/analysis"""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
            "service_name": self.service_name,
            "agent_name": self.agent_name,
            "operation": self.operation,
        }


@dataclass
class TraceData:
    """Complete trace data including all spans"""

    trace_id: str
    root_span_id: str
    spans: list[TraceSpan] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration_ms: float | None = None
    service_count: int = 0
    total_spans: int = 0
    error_count: int = 0
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        """Convert trace to dictionary for storage"""
        return {
            "trace_id": self.trace_id,
            "root_span_id": self.root_span_id,
            "spans": [span.to_dict() for span in self.spans],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "service_count": self.service_count,
            "total_spans": self.total_spans,
            "error_count": self.error_count,
            "status": self.status,
        }


class TraceCollector:
    """
    OpenTelemetry-based trace collector for distributed tracing.

    Features:
    - Multiple exporter support (Jaeger, OTLP, custom)
    - Automatic span creation and correlation
    - Baggage propagation for distributed context
    - Performance monitoring integration
    - Error tracking and alerting
    """

    def __init__(self, service_name: str = "justnews-agent", agent_name: str = ""):
        self.service_name = service_name
        self.agent_name = agent_name
        self.config = get_config()
        self.metrics = JustNewsMetrics(self.agent_name)

        # Initialize OpenTelemetry (best-effort) — skip if OTel unavailable
        if _OTEL_AVAILABLE:
            try:
                self._setup_tracing()
            except Exception as e:
                # Prevent tracing setup failures from breaking service in test/CI envs
                logger.warning("Trace setup failed; tracing disabled: %s", e)
                self._setup_tracing = lambda *a, **k: None
        else:
            logger.debug(
                "OpenTelemetry not available; running TraceCollector in no-op mode"
            )
            # Replace heavy methods with no-ops to avoid downstream errors
            self._setup_tracing = lambda *a, **k: None
            self.start_trace = lambda *a, **k: TraceContext(trace_id="0", span_id="0")
            self.start_span = lambda *a, **k: TraceContext(trace_id="0", span_id="0")
            self.end_span = lambda *a, **k: None
            self.record_event = lambda *a, **k: None

        # Trace storage
        self.active_traces: dict[str, TraceData] = {}
        self.completed_traces: dict[str, TraceData] = {}
        self.max_active_traces = 1000
        self.trace_retention_hours = 24

        # Performance tracking
        self.collection_latency = self.metrics._get_or_create_histogram("trace_collection_latency_seconds")
        self.span_count = self.metrics._get_or_create_counter("trace_spans_total")
        self.trace_count = self.metrics._get_or_create_counter(
            "traces_total", "Total number of traces processed", ["status"]
        )

        logger.info(
            f"TraceCollector initialized for service: {service_name}, agent: {agent_name}"
        )

    def _setup_tracing(self):
        """Setup OpenTelemetry tracing infrastructure"""
        global _trace_provider, _tracer

        if _trace_provider is None:
            # Create resource
            resource = Resource.create(
                {
                    ResourceAttributes.SERVICE_NAME: self.service_name,
                    ResourceAttributes.SERVICE_VERSION: "1.0.0",
                    "agent.name": self.agent_name,
                }
            )

            # Create trace provider
            _trace_provider = TracerProvider(resource=resource)

            # Setup exporters based on configuration
            exporters = self._create_exporters()
            for exporter in exporters:
                span_processor = BatchSpanProcessor(exporter)
                _trace_provider.add_span_processor(span_processor)

            # Set global trace provider
            trace.set_tracer_provider(_trace_provider)

        # Get tracer
        _tracer = trace.get_tracer(__name__)

        # Setup propagators
        trace.set_global_textmap(TraceContextTextMapPropagator())
        # Note: W3CBaggagePropagator setup would go here if needed

    def _create_exporters(self) -> list[Any]:
        """Create configured trace exporters"""
        exporters = []
        tracing_config = self.config.get("tracing", {})

        # Jaeger exporter
        if tracing_config.get("jaeger_enabled", True):
            jaeger_endpoint = tracing_config.get(
                "jaeger_endpoint", "http://localhost:14268/api/traces"
            )
            jaeger_exporter = JaegerExporter(
                agent_host_name="localhost",
                agent_port=6831,
            )
            exporters.append(jaeger_exporter)
            logger.info(f"Jaeger exporter configured: {jaeger_endpoint}")

        # OTLP exporter
        if tracing_config.get("otlp_enabled", False):
            otlp_endpoint = tracing_config.get("otlp_endpoint", "http://localhost:4317")
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            exporters.append(otlp_exporter)
            logger.info(f"OTLP exporter configured: {otlp_endpoint}")

        # Custom file exporter for development
        if tracing_config.get("file_export_enabled", True):
            # We'll implement a custom file exporter
            pass

        return exporters

    def start_trace(
        self, name: str, attributes: dict[str, Any] | None = None
    ) -> TraceContext:
        """
        Start a new trace with root span.

        Args:
            name: Name of the root operation
            attributes: Additional attributes for the trace

        Returns:
            TraceContext for the new trace
        """
        with self.collection_latency.time("start_trace"):
            span = _tracer.start_span(name, kind=SpanKind.INTERNAL)
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            # Create trace data
            trace_id = hex(span.get_span_context().trace_id)[2:]
            span_id = hex(span.get_span_context().span_id)[2:]

            trace_data = TraceData(trace_id=trace_id, root_span_id=span_id)

            # Store active trace
            if len(self.active_traces) < self.max_active_traces:
                self.active_traces[trace_id] = trace_data

            span.set_attribute("trace.root", True)
            span.set_attribute("service.name", self.service_name)
            span.set_attribute("agent.name", self.agent_name)

            trace_context = TraceContext.from_opentelemetry(span.get_span_context())

            self.trace_count.labels(status="started").inc()
            logger.debug(f"Started trace: {trace_id}, span: {span_id}")

            return trace_context

    def start_span(
        self,
        name: str,
        parent_context: TraceContext | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> TraceContext:
        """
        Start a new span within an existing trace.

        Args:
            name: Name of the span operation
            parent_context: Parent trace context
            attributes: Additional attributes for the span

        Returns:
            TraceContext for the new span
        """
        with self.collection_latency.time("start_span"):
            # Set parent context if provided
            if parent_context and _OTEL_AVAILABLE and trace is not None:
                # Create span context from parent. We guard at runtime so tests
                # without OpenTelemetry won't try to evaluate trace.SpanContext.
                span_context = trace.SpanContext(
                    trace_id=int(parent_context.trace_id, 16),
                    span_id=int(parent_context.span_id, 16),
                    is_remote=True,
                )
                span = _tracer.start_span(
                    name, context=span_context, kind=SpanKind.INTERNAL
                )
            else:
                span = _tracer.start_span(name, kind=SpanKind.INTERNAL)

            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)

            span.set_attribute("service.name", self.service_name)
            span.set_attribute("agent.name", self.agent_name)

            trace_context = TraceContext.from_opentelemetry(span.get_span_context())

            self.span_count.labels(service=self.service_name, status="started").inc()
            logger.debug(
                f"Started span: {trace_context.span_id} in trace: {trace_context.trace_id}"
            )

            return trace_context

    def end_span(
        self,
        context: TraceContext,
        status: str = "ok",
        attributes: dict[str, Any] | None = None,
    ):
        """
        End a span and record completion.

        Args:
            context: Trace context of the span to end
            status: Completion status ("ok", "error", "cancelled")
            attributes: Additional attributes to set before ending
        """
        with self.collection_latency.time("end_span"):
            # Get current span from context
            if _OTEL_AVAILABLE and trace is not None:
                span_context = trace.SpanContext(
                    trace_id=int(context.trace_id, 16),
                    span_id=int(context.span_id, 16),
                    is_remote=True,
                )
            else:
                # In degraded / no-op mode there's no actual span context to construct.
                span_context = None

            # Get current span (this is a simplified approach)
            # In a real implementation, you'd need to maintain span references
            current_span = trace.get_current_span()
            if (
                current_span
                and current_span.get_span_context().span_id == span_context.span_id
            ):
                if attributes:
                    for key, value in attributes.items():
                        current_span.set_attribute(key, value)

                if status == "error":
                    current_span.set_status(Status(StatusCode.ERROR))
                elif status == "ok":
                    current_span.set_status(Status(StatusCode.OK))

                current_span.end()

                self.span_count.labels(service=self.service_name, status=status).inc()
                logger.debug(f"Ended span: {context.span_id}, status: {status}")

    def record_event(
        self, context: TraceContext, name: str, attributes: dict[str, Any] | None = None
    ):
        """
        Record an event within a span.

        Args:
            context: Trace context
            name: Event name
            attributes: Event attributes
        """
        current_span = trace.get_current_span()
        if current_span:
            current_span.add_event(name, attributes or {})

    def inject_context(self, context: TraceContext) -> dict[str, str]:
        """
        Inject trace context into headers for distributed propagation.

        Args:
            context: Trace context to inject

        Returns:
            Dictionary of headers containing trace context
        """
        headers = {}
        TraceContextTextMapPropagator().inject(headers, context)
        return headers

    def extract_context(self, headers: dict[str, str]) -> TraceContext | None:
        """
        Extract trace context from headers.

        Args:
            headers: Headers containing trace context

        Returns:
            Extracted TraceContext or None
        """
        try:
            carrier = dict(headers)
            span_context = TraceContextTextMapPropagator().extract(carrier)
            if span_context:
                return TraceContext.from_opentelemetry(span_context)
        except Exception as e:
            logger.warning(f"Failed to extract trace context: {e}")
        return None

    def get_active_traces(self) -> list[TraceData]:
        """Get list of currently active traces"""
        return list(self.active_traces.values())

    def get_completed_traces(self, limit: int = 100) -> list[TraceData]:
        """Get list of recently completed traces"""
        traces = list(self.completed_traces.values())
        return traces[-limit:] if len(traces) > limit else traces

    def get_trace(self, trace_id: str) -> TraceData | None:
        """Get trace data by ID"""
        return self.active_traces.get(trace_id) or self.completed_traces.get(trace_id)

    async def cleanup_old_traces(self):
        """Cleanup old completed traces based on retention policy"""
        cutoff_time = datetime.now(UTC) - timedelta(hours=self.trace_retention_hours)
        to_remove = []

        for trace_id, trace_data in self.completed_traces.items():
            if trace_data.end_time and trace_data.end_time < cutoff_time:
                to_remove.append(trace_id)

        for trace_id in to_remove:
            del self.completed_traces[trace_id]

        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old traces")

    def get_stats(self) -> dict[str, Any]:
        """Get tracing statistics"""
        return {
            "active_traces": len(self.active_traces),
            "completed_traces": len(self.completed_traces),
            "total_traces": len(self.active_traces) + len(self.completed_traces),
            "max_active_traces": self.max_active_traces,
            "retention_hours": self.trace_retention_hours,
        }


# Global collector instance
_collector = None


def get_trace_collector(
    service_name: str = "justnews-agent", agent_name: str = ""
) -> TraceCollector:
    """Get or create global trace collector instance"""
    global _collector
    if _collector is None:
        _collector = TraceCollector(service_name, agent_name)
    return _collector


# Convenience functions for easy tracing
def start_trace(name: str, attributes: dict[str, Any] | None = None) -> TraceContext:
    """Convenience function to start a new trace"""
    collector = get_trace_collector()
    return collector.start_trace(name, attributes)


def start_span(
    name: str,
    parent_context: TraceContext | None = None,
    attributes: dict[str, Any] | None = None,
) -> TraceContext:
    """Convenience function to start a new span"""
    collector = get_trace_collector()
    return collector.start_span(name, parent_context, attributes)


def end_span(
    context: TraceContext, status: str = "ok", attributes: dict[str, Any] | None = None
):
    """Convenience function to end a span"""
    collector = get_trace_collector()
    collector.end_span(context, status, attributes)


def record_event(
    context: TraceContext, name: str, attributes: dict[str, Any] | None = None
):
    """Convenience function to record an event"""
    collector = get_trace_collector()
    collector.record_event(context, name, attributes)


# Context manager for automatic span management
class traced_span:
    """Context manager for automatic span lifecycle management"""

    def __init__(
        self,
        name: str,
        parent_context: TraceContext | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        self.name = name
        self.parent_context = parent_context
        self.attributes = attributes or {}
        self.context = None

    def __enter__(self):
        self.context = start_span(self.name, self.parent_context, self.attributes)
        return self.context

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            end_span(self.context, "error", {"error": str(exc_val)})
        else:
            end_span(self.context, "ok")
