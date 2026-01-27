"""OpenTelemetry bootstrap helpers for JustNews services."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)

try:  # Optional dependency: we only configure OpenTelemetry when installed.
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    # Instrumentation packages
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import (
        DEPLOYMENT_ENVIRONMENT,
        SERVICE_NAME,
        Resource,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except ImportError:  # pragma: no cover - optional dependency
    trace = None  # type: ignore
    Resource = None  # type: ignore
    TracerProvider = None  # type: ignore
    BatchSpanProcessor = None  # type: ignore
    OTLPSpanExporter = None  # type: ignore
    FastAPIInstrumentor = None  # type: ignore
    RequestsInstrumentor = None  # type: ignore


@dataclass
class _OtelState:
    enabled: bool = False
    service_name: str = "justnews-service"
    tracer_name: str = "justnews"


_STATE = _OtelState()


def _parse_headers(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    if raw.strip().startswith("{"):
        try:
            parsed = json.loads(raw)
            return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse JSON OTLP headers, falling back to CSV format"
            )
    headers: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            headers[key] = value
    return headers


def init_telemetry(
    service_name: str, *, resource_attributes: dict[str, Any] | None = None
) -> bool:
    """Configure OpenTelemetry tracing exporters."""
    if trace is None:
        logger.debug("OpenTelemetry SDK not installed; skipping instrumentation")
        return False

    if _STATE.enabled:
        return True

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "127.0.0.1:4317")
    insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() in {
        "1",
        "true",
        "yes",
    }
    headers = _parse_headers(os.environ.get("OTEL_EXPORTER_OTLP_HEADERS"))

    resource_attrs = {
        SERVICE_NAME: service_name,
        DEPLOYMENT_ENVIRONMENT: os.environ.get("DEPLOYMENT_ENVIRONMENT", "dev"),
        "justnews.repo_commit": os.environ.get("GIT_COMMIT", "unknown"),
    }
    for key, value in (resource_attributes or {}).items():
        if value is not None:
            resource_attrs[key] = value

    resource = Resource.create(resource_attrs)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure, headers=headers)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(tracer_provider)

    _STATE.enabled = True
    _STATE.service_name = service_name
    _STATE.tracer_name = f"justnews.{service_name}"
    logger.info(
        "OpenTelemetry tracing enabled (endpoint=%s, service=%s)",
        endpoint,
        service_name,
    )
    return True


def instrument_requests() -> None:
    """Enable auto-instrumentation for the requests library."""
    if not _STATE.enabled or RequestsInstrumentor is None:
        return

    RequestsInstrumentor().instrument()
    logger.debug("Requests library instrumented with OpenTelemetry")


def instrument_fastapi(app: Any) -> None:
    """
    Enable auto-instrumentation for a FastAPI application.
    
    Args:
        app: The FastAPI application instance to instrument.
    """
    if not _STATE.enabled or FastAPIInstrumentor is None:
        return

    FastAPIInstrumentor.instrument_app(app)
    logger.debug("FastAPI application instrumented with OpenTelemetry")


def is_enabled() -> bool:
    return _STATE.enabled


def get_tracer(name: str | None = None):
    if trace is None:
        raise RuntimeError("OpenTelemetry SDK not installed")
    tracer_name = name or _STATE.tracer_name
    return trace.get_tracer(tracer_name)


@contextmanager
def span_context(operation_name: str, *, attributes: dict[str, Any] | None = None):
    if not _STATE.enabled or trace is None:
        yield None
        return

    tracer = get_tracer()
    with tracer.start_as_current_span(operation_name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


def inject_trace_headers(carrier: dict[str, str]):
    """Inject the current span context into the provided carrier headers."""
    if not _STATE.enabled or trace is None:
        return carrier

    span = trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return carrier

    carrier["traceparent"] = span_context.trace_id.to_bytes(16, "big").hex()
    carrier["span-id"] = span_context.span_id.to_bytes(8, "big").hex()
    return carrier


@contextmanager
def noop_span(operation_name: str, *_args: Iterable[Any], **_kwargs: Any):  # noqa: D401 - simple placeholder
    yield None


def span_or_noop(operation_name: str):
    return span_context(operation_name) if _STATE.enabled else nullcontext()
