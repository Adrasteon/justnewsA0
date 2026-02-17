"""Lightweight Sentry integration wrapper for JustNews.

This module centralizes sentinel initialization and safe defaults so services
can opt-in without leaking secrets or sending noisy events by default.

Usage:
    from common.sentry_integration import init_sentry
    init_sentry("mcp_bus")

The function will read environment variables:
 - SENTRY_DSN (string): DSN for Sentry; when empty or unset Sentry is not initialized
 - SENTRY_TRACES_SAMPLE_RATE (float, default 0.0): sampling rate for tracing
 - SENTRY_ENV (string, default 'local') environment name to report into Sentry

The function is idempotent and safe to call multiple times.
"""

from __future__ import annotations

import logging
import os

_initialized = False


def _scrub_payload(event, hint):
    """Before-send hook to scrub potentially sensitive fields.

    Customize to your privacy policy. We remove request bodies by default and
    trim long string fields.
    """
    try:
        # Remove request body if present
        request = event.get("request")
        if request and "data" in request:
            request.pop("data", None)

        # Trim long messages
        if "message" in event:
            m = event["message"]
            if isinstance(m, dict) and "formatted" in m:
                if len(m["formatted"]) > 3000:
                    m["formatted"] = m["formatted"][:3000] + "..."

    except Exception:
        # Never fail initialization due to scrubbing logic
        logging.getLogger(__name__).exception("Sentry scrub hook failed")

    return event


def init_sentry(service_name: str, *, logger: logging.Logger | None = None) -> bool:
    """Initialize Sentry if SENTRY_DSN is provided.

    Returns True if Sentry was initialized and False otherwise. Initialization
    is idempotent and safe to call from multiple modules.
    """
    global _initialized
    if _initialized:
        return True

    dsn = os.environ.get("SENTRY_DSN", "")
    if not dsn:
        if logger:
            logger.debug("SENTRY_DSN not set — Sentry not initialized")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except Exception as exc:  # pragma: no cover - defensive
        if logger:
            logger.warning("sentry-sdk not installed: %s", exc)
        return False

    # Configure logging integration: capture only ERROR events as default
    sentry_logging = LoggingIntegration(level=None, event_level="ERROR")

    traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0"))
    environment = os.environ.get(
        "SENTRY_ENV", os.environ.get("DEPLOYMENT_ENVIRONMENT", "local")
    )

    try:
        sentry_sdk.init(
            dsn=dsn,
            integrations=[sentry_logging],
            traces_sample_rate=traces_sample_rate,
            environment=environment,
            release=os.environ.get("JUSTNEWS_RELEASE", None),
            before_send=_scrub_payload,
            # Safe default - do not capture personally identifying data by default
            send_default_pii=False,
        )

        _initialized = True
        if logger:
            logger.info(
                "Sentry initialized for %s (env=%s, sample_rate=%s)",
                service_name,
                environment,
                traces_sample_rate,
            )
        return True

    except Exception as exc:  # pragma: no cover - runtime
        if logger:
            logger.exception("Failed to initialize Sentry: %s", exc)
        return False
