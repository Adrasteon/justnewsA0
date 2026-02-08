"""Common graceful shutdown helper for JustNews agents.

Provides a small utility to register a `/shutdown` endpoint on a FastAPI app
that triggers a clean process shutdown (SIGINT) after responding. The handler
optionally requires a token provided via environment variable `SHUTDOWN_TOKEN`
for safety in shared networks.

Usage:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)

The endpoint is POST /shutdown and returns 202 immediately.
"""

from __future__ import annotations

import os
import signal
import threading
import time

from fastapi import FastAPI, HTTPException, Request

from common.observability import get_logger

logger = get_logger(__name__)


def _send_sigint_after_delay(delay: float = 0.5) -> None:
    """Sleep for `delay` seconds then send SIGINT to this process.

    Running this in a thread avoids blocking the request thread so the
    HTTP response can be returned immediately.
    """
    try:
        time.sleep(delay)
        os.kill(os.getpid(), signal.SIGINT)
    except Exception as e:
        logger.exception("shutdown_failed", error=str(e))


def register_shutdown_endpoint(
    app: FastAPI, path: str = "/shutdown", delay: float = 0.5
) -> None:
    """Register a POST endpoint on `app` that triggers a graceful shutdown.

    If environment variable `SHUTDOWN_TOKEN` is set, the endpoint requires the
    same token to be supplied in the `X-SHUTDOWN-TOKEN` header for protection.
    """

    token = os.environ.get("SHUTDOWN_TOKEN")

    async def _shutdown(request: Request):
        # If a token is configured, require it in the header
        if token:
            header = request.headers.get("x-shutdown-token")
            if not header or header != token:
                raise HTTPException(status_code=403, detail="Forbidden")

        # Spawn background thread to send SIGINT after a short delay
        thread = threading.Thread(
            target=_send_sigint_after_delay, args=(delay,), daemon=True
        )
        thread.start()
        return {"status": "shutting_down"}

    # Register the endpoint on the FastAPI app
    app.post(path)(_shutdown)
