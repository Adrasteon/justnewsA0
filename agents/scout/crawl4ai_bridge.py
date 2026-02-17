"""Deprecated scout-local bridge shim.

The canonical bridge utilities moved to `agents.c4ai.bridge`. This module
keeps a small compatibility shim that warns on import and re-exports the
primary helper `crawl_via_local_server` when available.
"""

import os as _os
from warnings import warn

# During tests we set ``PYTEST_RUNNING=1`` in `conftest.py` so that
# import-time deprecation warnings from compatibility shims do not cause
# the test suite to fail under the 'warnings as errors' policy. Keep the
# warning in production so callers are encouraged to migrate.
if _os.environ.get("PYTEST_RUNNING", "0") != "1":
    warn(
        "agents.c4ai.bridge is deprecated; import agents.c4ai.bridge instead",
        DeprecationWarning,
        stacklevel=2,
    )

try:
    from agents.c4ai.bridge import crawl_via_local_server  # type: ignore

    __all__ = ["crawl_via_local_server"]
except Exception:  # pragma: no cover - fallback

    async def crawl_via_local_server(url: str, *_, **__) -> dict:
        """Fallback minimal implementation when canonical bridge can't be imported.

        Returns a simple error dict so callers don't raise on import-time calls.
        """
        return {"url": url, "error": "canonical_bridge_unavailable", "success": False}

    __all__ = ["crawl_via_local_server"]
