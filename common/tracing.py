"""
Tracing utilities for JustNews agents.

This module provides high-level decorators and context managers to simplify
OpenTelemetry integration across the codebase. It wraps the low-level
opentelemetry API to ensure consistent span naming and attribute handling.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, TypeVar

from opentelemetry import propagate, trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, Status, StatusCode

from common.otel import _STATE

T = TypeVar("T")


def get_tracer(name: str | None = None) -> trace.Tracer:
    """
    Get a tracer instance for the current module.
    
    Args:
        name: Optional name for the tracer. If omitted, uses the global state
              service name or 'justnews'.
    """
    tracer_name = name or _STATE.tracer_name
    return trace.get_tracer(tracer_name)


def inject_trace_context(carrier: dict[str, Any]) -> None:
    """
    Inject the current trace context into a dictionary (e.g., for Redis/serialization).
    
    This handles keys as strings. If using with Redis/Kafka clients that require bytes,
    encoding may be needed by the caller.
    """
    if not _STATE.enabled:
        return
    propagate.inject(carrier)


def extract_trace_context(carrier: dict[str | bytes, Any]) -> Context:
    """
    Extract trace context from a dictionary (e.g., from Redis).
    
    Handles mixed string/bytes keys commonly found in Redis responses.
    """
    if not carrier:
        return propagate.extract({})

    # Standardize keys to strings for OTel propagator
    safe_carrier = {}
    for k, v in carrier.items():
        key_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
        val_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
        safe_carrier[key_str] = val_str

    return propagate.extract(safe_carrier)



def traced(
    name: str | None = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
    record_args: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to wrap a function execution in an OpenTelemetry span.

    Args:
        name: Custom name for the span. Defaults to function name.
        kind: The OpenTelemetry span kind (INTERNAL, CLIENT, SERVER, etc.).
        attributes: Dictionary of static attributes to add to the span.
        record_args: If True, attempts to record function arguments as span attributes.
                     Use with caution on functions receiving large data or secrets.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        module_name = func.__module__
        qualname = func.__qualname__
        span_name = name or f"{module_name}.{qualname}"

        tracer = get_tracer(module_name)

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> T:
                if not _STATE.enabled:
                    return await func(*args, **kwargs)

                with tracer.start_as_current_span(
                    span_name, kind=kind, attributes=attributes or {}
                ) as span:
                    if record_args:
                        _record_arguments(span, func, args, kwargs)

                    try:
                        return await func(*args, **kwargs)
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise
        else:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> T:
                if not _STATE.enabled:
                    return func(*args, **kwargs)

                with tracer.start_as_current_span(
                    span_name, kind=kind, attributes=attributes or {}
                ) as span:
                    if record_args:
                        _record_arguments(span, func, args, kwargs)

                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        raise

        return wrapper
    return decorator


@contextmanager
def trace_block(
    name: str,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
    attributes: dict[str, Any] | None = None,
) -> Generator[Span, None, None]:
    """
    Context manager to trace a specific block of code.

    Usage:
        with trace_block("gpu_inference", attributes={"model": "mistral"}):
            result = model.generate(...)
    """
    if not _STATE.enabled:
        yield trace.get_current_span()
        return

    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind, attributes=attributes) as span:
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


def _record_arguments(
    span: Span, func: Callable[..., Any], args: Any, kwargs: Any
) -> None:
    """Helper to safely record function arguments as attributes."""
    try:
        # Use inspect to map args to parameter names
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        for param_name, value in bound.arguments.items():
            # Skip 'self' or 'cls' for methods
            if param_name in ("self", "cls"):
                continue

            # Naive safety check: skip arguments that look like secrets
            if any(s in param_name.lower() for s in ("token", "key", "password", "secret", "auth")):
                span.set_attribute(f"arg.{param_name}", "[REDACTED]")
                continue

            # Convert complex types to string representation if needed
            if isinstance(value, (str, int, float, bool)):
                span.set_attribute(f"arg.{param_name}", value)
            else:
                span.set_attribute(f"arg.{param_name}", str(value)[:1024]) # Truncate large objects

    except Exception:
        # Never fail the app logic because of telemetry errors
        pass
