#!/usr/bin/env python3
"""
Distributed Tracing Module for JustNews
Provides tracing functionality for distributed operations across agents
"""

import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from common.observability import get_logger

try:
    from common import otel
except ImportError:  # pragma: no cover - optional dependency
    otel = None

logger = get_logger(__name__)

# Context variables for trace propagation
current_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
current_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)
current_parent_span_id: ContextVar[str | None] = ContextVar(
    "parent_span_id", default=None
)


@dataclass
class TraceSpan:
    """Represents a single trace span"""

    trace_id: str
    span_id: str
    parent_span_id: str | None
    operation_name: str
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "started"

    def finish(self, status: str = "completed"):
        """Finish the span"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status

    def add_tag(self, key: str, value: Any):
        """Add a tag to the span"""
        self.tags[key] = value

    def add_metadata(self, key: str, value: Any):
        """Add metadata to the span"""
        self.metadata[key] = value


class TraceContext:
    """Manages trace context for distributed operations"""

    def __init__(self, trace_id: str | None = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.spans: dict[str, TraceSpan] = {}
        self.active_spans: list = []

    def start_span(
        self, operation_name: str, parent_span_id: str | None = None
    ) -> TraceSpan:
        """Start a new span"""
        span_id = str(uuid.uuid4())
        span = TraceSpan(
            trace_id=self.trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id
            or (self.active_spans[-1].span_id if self.active_spans else None),
            operation_name=operation_name,
            start_time=time.time(),
        )

        self.spans[span_id] = span
        self.active_spans.append(span)
        return span

    def finish_span(self, span_id: str, status: str = "completed"):
        """Finish a span"""
        if span_id in self.spans:
            span = self.spans[span_id]
            span.finish(status)

            # Remove from active spans
            if self.active_spans and self.active_spans[-1].span_id == span_id:
                self.active_spans.pop()

    def get_active_span(self) -> TraceSpan | None:
        """Get the currently active span"""
        return self.active_spans[-1] if self.active_spans else None

    def get_trace_summary(self) -> dict[str, Any]:
        """Get a summary of the trace"""
        total_spans = len(self.spans)
        completed_spans = sum(
            1 for span in self.spans.values() if span.status == "completed"
        )
        failed_spans = sum(1 for span in self.spans.values() if span.status == "failed")

        total_duration = 0
        if self.spans:
            start_times = [span.start_time for span in self.spans.values()]
            end_times = [span.end_time or time.time() for span in self.spans.values()]
            total_duration = (max(end_times) - min(start_times)) * 1000

        return {
            "trace_id": self.trace_id,
            "total_spans": total_spans,
            "completed_spans": completed_spans,
            "failed_spans": failed_spans,
            "total_duration_ms": total_duration,
            "spans": [
                {
                    "span_id": span.span_id,
                    "operation": span.operation_name,
                    "duration_ms": span.duration_ms,
                    "status": span.status,
                    "tags": span.tags,
                }
                for span in self.spans.values()
            ],
        }


# Global trace context
_current_trace_context: TraceContext | None = None


def start_trace(operation_name: str, trace_id: str | None = None) -> TraceSpan:
    """Start a new trace"""
    global _current_trace_context
    _current_trace_context = TraceContext(trace_id)
    span = _current_trace_context.start_span(operation_name)

    # Set context variables
    current_trace_id.set(_current_trace_context.trace_id)
    current_span_id.set(span.span_id)

    logger.debug(
        f"Started trace {span.trace_id} with span {span.span_id} for operation '{operation_name}'"
    )
    return span


def get_current_trace_context() -> TraceContext | None:
    """Get the current trace context"""
    return _current_trace_context


def get_trace_context() -> dict[str, Any]:
    """Get current trace context information"""
    trace_id = current_trace_id.get()
    span_id = current_span_id.get()
    parent_span_id = current_parent_span_id.get()

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "has_active_trace": trace_id is not None,
    }


def create_child_span(operation_name: str) -> TraceSpan | None:
    """Create a child span in the current trace"""
    global _current_trace_context
    if _current_trace_context is None:
        logger.warning("No active trace context, cannot create child span")
        return None

    span = _current_trace_context.start_span(operation_name)
    current_span_id.set(span.span_id)
    current_parent_span_id.set(span.parent_span_id)

    logger.debug(f"Created child span {span.span_id} for operation '{operation_name}'")
    return span


def finish_current_span(status: str = "completed"):
    """Finish the current active span"""
    global _current_trace_context
    span_id = current_span_id.get()

    if _current_trace_context and span_id:
        _current_trace_context.finish_span(span_id, status)
        logger.debug(f"Finished span {span_id} with status '{status}'")

        # Update context variables
        if _current_trace_context.active_spans:
            current_span_id.set(_current_trace_context.active_spans[-1].span_id)
        else:
            current_span_id.set(None)


def finish_trace() -> dict[str, Any] | None:
    """Finish the current trace and return summary"""
    global _current_trace_context

    if _current_trace_context is None:
        logger.warning("No active trace to finish")
        return None

    # Finish all active spans
    while _current_trace_context.active_spans:
        span = _current_trace_context.active_spans[-1]
        _current_trace_context.finish_span(span.span_id, "completed")

    summary = _current_trace_context.get_trace_summary()

    # Clear context
    _current_trace_context = None
    current_trace_id.set(None)
    current_span_id.set(None)
    current_parent_span_id.set(None)

    logger.info(
        f"Finished trace {summary['trace_id']} with {summary['total_spans']} spans in {summary['total_duration_ms']:.2f}ms"
    )
    return summary


def add_span_tag(key: str, value: Any):
    """Add a tag to the current active span"""
    global _current_trace_context
    span_id = current_span_id.get()

    if _current_trace_context and span_id and span_id in _current_trace_context.spans:
        _current_trace_context.spans[span_id].add_tag(key, value)


def add_span_metadata(key: str, value: Any):
    """Add metadata to the current active span"""
    global _current_trace_context
    span_id = current_span_id.get()

    if _current_trace_context and span_id and span_id in _current_trace_context.spans:
        _current_trace_context.spans[span_id].add_metadata(key, value)


def record_exception(exception: Exception):
    """Record an exception in the current span"""
    global _current_trace_context
    span_id = current_span_id.get()

    if _current_trace_context and span_id and span_id in _current_trace_context.spans:
        span = _current_trace_context.spans[span_id]
        span.add_tag("error", True)
        span.add_metadata("exception_type", type(exception).__name__)
        span.add_metadata("exception_message", str(exception))

        # Finish span with error status
        _current_trace_context.finish_span(span_id, "error")


# Context manager for automatic span management
class trace_span:
    """Context manager for tracing spans"""

    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.span = None
        self._otel_cm = None

    def __enter__(self):
        self.span = create_child_span(self.operation_name)
        if otel and getattr(otel, "is_enabled", lambda: False)():
            self._otel_cm = otel.span_context(self.operation_name)
            if self._otel_cm is not None:
                self._otel_cm.__enter__()
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and self.span:
            # Record exception if one occurred
            record_exception(exc_val)
        else:
            finish_current_span("completed")
        if self._otel_cm is not None:
            self._otel_cm.__exit__(exc_type, exc_val, exc_tb)


# Decorator for automatic function tracing
def traced(operation_name: str | None = None):
    """Decorator to automatically trace function calls"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            with trace_span(op_name):
                try:
                    result = func(*args, **kwargs)
                    add_span_metadata("result_type", type(result).__name__)
                    return result
                except Exception as e:
                    record_exception(e)
                    raise

        return wrapper

    return decorator


# Integration with logging
def setup_tracing_logging():
    """Set up logging integration with tracing"""

    class TracingLogFilter(logging.Filter):
        def filter(self, record):
            # Add trace context to log records
            trace_context = get_trace_context()
            if trace_context["has_active_trace"]:
                record.trace_id = trace_context["trace_id"]
                record.span_id = trace_context["span_id"]
            else:
                record.trace_id = None
                record.span_id = None
            return True

    # Add filter to root logger
    root_logger = get_logger(__name__)
    root_logger.addFilter(TracingLogFilter())


# Initialize tracing logging on import
setup_tracing_logging()
