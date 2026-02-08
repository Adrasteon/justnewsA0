"""Deprecated shim / compatibility wrapper for crawl4ai used by scout.

This module attempts to re-export the canonical `agents.c4ai.server` API so
existing imports keep working. When the canonical module is not present we
provide a small, safe fallback FastAPI app that exposes `/health` and `/crawl`.

The fallback is intentionally minimal (it returns 503 for crawl if the
crawl4ai package is not available) so this shim can be used during
transitions without introducing significant runtime surface area.
"""

from __future__ import annotations

import os
from typing import Any
from warnings import warn

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Prefer canonical server when present
if os.environ.get("PYTEST_RUNNING", "0") != "1":
    warn(
        "agents.c4ai.server is deprecated; import agents.c4ai.server instead",
        DeprecationWarning,
        stacklevel=2,
    )

try:
    # Re-export canonical server if available
    from agents.c4ai.server import CrawlRequest, app, crawl, health  # type: ignore

    __all__ = ["app", "CrawlRequest", "crawl", "health"]
except Exception:
    # Provide a minimal fallback implementation so imports don't break
    app = FastAPI(title="deprecated-crawl4ai-bridge")

    class CrawlRequest(BaseModel):
        urls: list[str]
        mode: str = "standard"
        use_llm: bool = True

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Basic liveness probe for the fallback shim."""
        return {"status": "deprecated", "service": "crawl4ai-bridge"}

    @app.post("/crawl")
    async def crawl(req: CrawlRequest) -> dict[str, Any]:
        """Fallback /crawl endpoint.

        When the real `crawl4ai` package is available the canonical
        implementation should be used (and this shim won't be executed).
        The fallback returns 503 if the heavy runtime is not installed.
        """
        try:
            # Heavy optional dependency; imported at runtime only when used
            from crawl4ai import (  # type: ignore
                AsyncWebCrawler,
                BrowserConfig,
                CacheMode,
                CrawlerRunConfig,
            )
        except Exception as exc:  # pragma: no cover - environment may not have crawl4ai
            raise HTTPException(
                status_code=503, detail=f"crawl4ai not available: {exc}"
            ) from exc

        results: list[dict[str, Any]] = []

        # Run a very small, defensive crawl so the fallback can operate when
        # crawl4ai is installed. This keeps the code path simple and auditable.
        browser_cfg = (
            BrowserConfig(headless=True) if hasattr(BrowserConfig, "__init__") else None
        )
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            for url in req.urls:
                try:
                    res = await crawler.arun(
                        url, config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
                    )
                    results.append(
                        {
                            "url": getattr(res, "url", url),
                            "title": getattr(res, "title", None),
                            "status_code": getattr(res, "status_code", None),
                            "success": getattr(res, "success", True),
                        }
                    )
                except Exception as exc:  # don't fail the whole request on one URL
                    results.append({"url": url, "error": str(exc), "success": False})

        return {"results": results}

    __all__ = ["app", "CrawlRequest", "crawl", "health"]
