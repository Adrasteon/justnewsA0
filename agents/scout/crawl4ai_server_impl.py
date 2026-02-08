"""Deprecated implementation copy for scout-local Crawl4AI server.

This module used to contain a standalone implementation. The canonical
bridge lives at `agents.c4ai.server`. Keep this shim for compatibility
only; it warns on import and re-exports the canonical API when possible.
"""

import os as _os
from warnings import warn

# During tests, `conftest.py` sets ``PYTEST_RUNNING=1`` so import-time
# deprecation warnings from compatibility shims won't fail the test suite.
if _os.environ.get("PYTEST_RUNNING", "0") != "1":
    warn(
        "agents.c4ai.server_impl is deprecated; import agents.c4ai.server instead",
        DeprecationWarning,
        stacklevel=2,
    )

try:
    from agents.c4ai.server import CrawlRequest, app, crawl, health  # type: ignore

    __all__ = ["app", "CrawlRequest", "crawl", "health"]
except Exception:  # pragma: no cover - fallback
    from fastapi import FastAPI

    app = FastAPI(title="deprecated-crawl4ai-impl")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "deprecated", "service": "crawl4ai-bridge-impl"}

    __all__ = ["app", "health"]
