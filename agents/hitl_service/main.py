"""Entry point for running the HITL service under systemd or CLI."""

from __future__ import annotations

import os
import sys

try:
    import uvicorn
except Exception as exc:  # pragma: no cover - import guard for clearer error
    raise RuntimeError("uvicorn is required to run the HITL service") from exc


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def main() -> None:
    """Run the HITL FastAPI application via uvicorn."""
    host = os.environ.get("HITL_SERVICE_HOST", "0.0.0.0")
    try:
        port = int(
            os.environ.get("HITL_SERVICE_PORT", os.environ.get("HITL_PORT", "8019"))
        )
    except ValueError as exc:  # pragma: no cover - configuration error path
        raise RuntimeError("HITL_SERVICE_PORT must be an integer") from exc

    log_level = os.environ.get("HITL_SERVICE_LOG_LEVEL", "info")
    reload_enabled = _as_bool(os.environ.get("HITL_SERVICE_RELOAD"), default=False)

    uvicorn.run(
        "agents.hitl_service.app:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=reload_enabled,
        reload_includes=None,
    )


if __name__ == "__main__":  # pragma: no cover - manual invocation
    try:
        main()
    except Exception as exc:
        print(f"Failed to start HITL service: {exc}", file=sys.stderr)
        raise
