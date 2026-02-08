"""Bridge utilities to interact with a local Crawl4AI server or run AsyncWebCrawler in-process.

This was previously under `agents/scout`; it's moved here for clearer separation
so multiple agents can import `agents.c4ai.bridge`.
"""

from __future__ import annotations

import os
from typing import Any

try:
    import aiohttp
except Exception:  # pragma: no cover - aiohttp optional
    aiohttp = None

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
except Exception:
    AsyncWebCrawler = None
    BrowserConfig = None
    CrawlerRunConfig = None
    CacheMode = None


async def crawl_via_local_server(
    url: str,
    *,
    mode: str = "standard",
    use_llm: bool = True,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Call a local Crawl4AI HTTP server (systemd-managed) and return a normalized result.

    Falls back to in-process AsyncWebCrawler if the HTTP endpoint is not reachable
    or if aiohttp/crawl4ai are not available.
    """
    if base_url is None:
        host = os.getenv("CRAWL4AI_HOST", "127.0.0.1")
        port = os.getenv("CRAWL4AI_PORT", "3308")
        base_url = f"http://{host}:{port}"

    payload = {"urls": [url], "mode": mode, "use_llm": use_llm}

    # Prefer local HTTP server when available
    if aiohttp is not None:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{base_url}/crawl", json=payload, timeout=60
                ) as resp:
                    data = await resp.json()
                    if isinstance(data, dict) and data.get("results"):
                        return data["results"][0]
                    return {"url": url, "error": "unexpected_response", "raw": data}
        except Exception:
            # Fallthrough to in-process attempt
            pass

    # In-process fallback
    if AsyncWebCrawler is None:
        return {"url": url, "error": "crawl4ai_unavailable", "success": False}

    try:
        browser_conf = BrowserConfig(headless=True) if BrowserConfig else None
        run_conf = (
            CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
            if CrawlerRunConfig and CacheMode
            else None
        )
        async with AsyncWebCrawler(config=browser_conf) as crawler:
            res = await crawler.arun(url, config=run_conf)
            return {
                "url": getattr(res, "url", url),
                "markdown": getattr(res, "markdown", None),
                "html": getattr(res, "html", None),
                "title": getattr(res, "title", None),
                "links": getattr(res, "links", []),
                "status_code": getattr(res, "status_code", None),
                "success": getattr(res, "success", True),
            }
    except Exception as e:
        return {"url": url, "error": str(e), "success": False}
