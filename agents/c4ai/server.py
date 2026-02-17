"""Crawl4AI bridge HTTP server.

Small, robust FastAPI wrapper for local Crawl4AI usage. This implementation
performs lazy imports of optional crawler enhancements (UA rotation,
proxy manager, stealth browser, modal/cookie handler, paywall detector,
robots checker and rate limiter) and uses a small SQLite-based
paywall aggregator if available to avoid recording single transient
detections immediately.

The server exposes:
- GET /health
- POST /crawl  -> accepts JSON {"urls":[...], "mode":"...", "use_llm":true}

The implementation is defensive: missing optional modules are ignored and
the endpoint will return a 503 if the core `crawl4ai` package is missing.
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="JustNews Crawl4AI Bridge")


class CrawlRequest(BaseModel):
    urls: list[str]
    mode: str = "standard"
    use_llm: bool = True


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "service": "crawl4ai-bridge"}


def _require_api_token(
    authorization: str | None = Header(None), x_api_token: str | None = Header(None)
):
    expected = os.environ.get("CRAWLER_API_TOKEN")
    if not expected:
        return None
    token = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            token = authorization.split(None, 1)[1].strip()
        else:
            token = authorization.strip()
    if not token and x_api_token:
        token = x_api_token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing API token")
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API token")
    return None


@app.post("/crawl")
async def crawl(
    req: CrawlRequest, token_ok: None = Depends(_require_api_token)
) -> dict[str, Any]:
    # core dependency
    try:
        from crawl4ai import (  # type: ignore
            AsyncWebCrawler,
            BrowserConfig,
            CacheMode,
            CrawlerRunConfig,
        )
    except (
        Exception
    ) as exc:  # pragma: no cover - dependency may be missing in test envs
        raise HTTPException(
            status_code=503, detail=f"crawl4ai not available: {exc}"
        ) from exc

    # best-effort optional helpers
    def _get_crawler_utils_module():
        module = sys.modules.get("agents.crawler.crawler_utils")
        if module is not None:
            return module
        try:
            return importlib.import_module("agents.crawler.crawler_utils")
        except Exception:
            return None

    crawler_utils_module = _get_crawler_utils_module()

    record_paywall_detection = (
        getattr(crawler_utils_module, "record_paywall_detection", None)
        if crawler_utils_module
        else None
    )  # type: ignore[index]
    RobotsChecker = (
        getattr(crawler_utils_module, "RobotsChecker", None)
        if crawler_utils_module
        else None
    )  # type: ignore[assignment]
    RateLimiter = (
        getattr(crawler_utils_module, "RateLimiter", None)
        if crawler_utils_module
        else None
    )  # type: ignore[assignment]

    try:
        from agents.crawler.paywall_aggregator import (
            increment_and_check,  # type: ignore
        )
    except Exception:
        increment_and_check = None  # type: ignore

    try:
        from agents.crawler.enhancements.ua_rotation import (  # type: ignore
            UserAgentConfig,
            UserAgentProvider,
        )
    except Exception:
        UserAgentProvider = None  # type: ignore
        UserAgentConfig = None  # type: ignore

    try:
        from agents.crawler.enhancements.stealth_browser import (
            StealthBrowserFactory,  # type: ignore
        )
    except Exception:
        StealthBrowserFactory = None  # type: ignore

    try:
        from agents.crawler.enhancements.proxy_manager import (
            ProxyManager,  # type: ignore
        )
    except Exception:
        ProxyManager = None  # type: ignore

    try:
        from agents.crawler.enhancements.paywall_detector import (
            PaywallDetector,  # type: ignore
        )
    except Exception:
        PaywallDetector = None  # type: ignore

    try:
        from agents.crawler.enhancements.modal_handler import (
            ModalHandler,  # type: ignore
        )
    except Exception:
        ModalHandler = None  # type: ignore

    # runtime flags
    persist_paywalls = os.getenv("CRAWL4AI_PERSIST_PAYWALLS", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # instantiate helpers best-effort
    robots_checker = RobotsChecker() if RobotsChecker is not None else None
    rate_limiter = RateLimiter() if RateLimiter is not None else None
    modal_handler = ModalHandler() if ModalHandler is not None else None
    paywall_detector = PaywallDetector() if PaywallDetector is not None else None

    stealth_factory = None
    if StealthBrowserFactory is not None:
        try:
            stealth_factory = StealthBrowserFactory()
        except Exception:
            stealth_factory = None

    ua_provider = None
    if UserAgentProvider is not None and UserAgentConfig is not None:
        try:
            ua_cfg = UserAgentConfig(pool=[], per_domain_overrides={}, default=None)
            ua_provider = UserAgentProvider(ua_cfg)
        except Exception:
            ua_provider = None

    proxy_manager = None
    if ProxyManager is not None:
        try:
            proxy_manager = ProxyManager()
        except Exception:
            proxy_manager = None

    results: list[dict[str, Any]] = []

    # Per-URL crawling
    for url in req.urls:
        # robots check
        if robots_checker is not None:
            try:
                if not robots_checker.is_allowed(url):
                    results.append(
                        {"url": url, "error": "disallowed_by_robots", "success": False}
                    )
                    continue
            except Exception:
                pass

        # rate limiter
        if rate_limiter is not None:
            try:
                domain = urlparse(url).netloc
                rate_limiter.acquire(domain)
            except Exception:
                pass

        # Build browser kwargs
        browser_kwargs: dict = {"headless": True}
        # user-agent
        try:
            if ua_provider is not None:
                ua = getattr(ua_provider, "choose", lambda **k: None)(domain=None)
                if ua:
                    browser_kwargs["user_agent"] = ua
            elif stealth_factory is not None:
                prof = getattr(stealth_factory, "random_profile", lambda: None)()
                if prof is not None:
                    browser_kwargs["user_agent"] = getattr(prof, "user_agent", None)
        except Exception:
            pass

        # proxy
        try:
            if proxy_manager is not None:
                p = None
                if hasattr(proxy_manager, "next_proxy"):
                    p = proxy_manager.next_proxy()
                elif hasattr(proxy_manager, "get_proxy"):
                    p = proxy_manager.get_proxy()
                if p is not None:
                    browser_kwargs["proxy"] = getattr(p, "url", None) or str(p)
        except Exception:
            pass

        # Construct browser config (safe fallback)
        try:
            browser_cfg = BrowserConfig(**browser_kwargs)
        except Exception:
            try:
                browser_cfg = BrowserConfig(headless=True)
                for k, v in browser_kwargs.items():
                    try:
                        setattr(browser_cfg, k, v)
                    except Exception:
                        pass
            except Exception:
                browser_cfg = None

        if browser_cfg is None:
            results.append(
                {
                    "url": url,
                    "error": "unable_to_construct_browser_config",
                    "success": False,
                }
            )
            continue

        # run crawler for this URL
        try:
            async with AsyncWebCrawler(config=browser_cfg) as crawler:
                try:
                    run_conf = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
                    res = await crawler.arun(url, config=run_conf)
                except Exception:
                    res = await crawler.arun(url)

                html = getattr(res, "html", None) or ""
                markdown = getattr(res, "markdown", None)

                # modal handling
                if modal_handler is not None and html:
                    try:
                        mh = modal_handler.process(html)
                        html = getattr(mh, "cleaned_html", html)
                    except Exception:
                        pass

                # paywall detection
                skip_ingest = False
                paywall_meta = None
                if paywall_detector is not None:
                    try:
                        pw_res = await paywall_detector.analyze(
                            url=url, html=html, text=markdown
                        )
                        skip_ingest = bool(getattr(pw_res, "should_skip", False))
                        paywall_meta = pw_res
                    except Exception:
                        pass

                # persistence: prefer aggregator if available
                if skip_ingest and persist_paywalls:
                    crawler_utils_module = _get_crawler_utils_module()
                    try:
                        domain = urlparse(url).netloc
                        if increment_and_check is not None:
                            try:
                                threshold = int(
                                    os.getenv("CRAWL4AI_PAYWALL_THRESHOLD", "3")
                                )
                            except Exception:
                                threshold = 3
                            try:
                                count, reached = increment_and_check(
                                    domain, threshold=threshold
                                )
                                record_fn = (
                                    getattr(
                                        crawler_utils_module,
                                        "record_paywall_detection",
                                        None,
                                    )
                                    if crawler_utils_module is not None
                                    else None
                                )
                                if record_fn is None:
                                    record_fn = record_paywall_detection
                                if reached and record_fn is not None:
                                    record_fn(
                                        source_id=None,
                                        domain=domain,
                                        skip_count=count,
                                        threshold=threshold,
                                        paywall_type="detected",
                                    )
                            except Exception:
                                record_fn = (
                                    getattr(
                                        crawler_utils_module,
                                        "record_paywall_detection",
                                        None,
                                    )
                                    if crawler_utils_module is not None
                                    else None
                                )
                                if record_fn is None:
                                    record_fn = record_paywall_detection
                                if record_fn is not None:
                                    try:
                                        record_fn(
                                            source_id=None,
                                            domain=domain,
                                            skip_count=1,
                                            threshold=1,
                                            paywall_type="detected",
                                        )
                                    except Exception:
                                        pass
                        else:
                            record_fn = (
                                getattr(
                                    crawler_utils_module,
                                    "record_paywall_detection",
                                    None,
                                )
                                if crawler_utils_module is not None
                                else None
                            )
                            if record_fn is None:
                                record_fn = record_paywall_detection
                            if record_fn is not None:
                                try:
                                    record_fn(
                                        source_id=None,
                                        domain=domain,
                                        skip_count=1,
                                        threshold=1,
                                        paywall_type="detected",
                                    )
                                except Exception:
                                    pass
                    except Exception:
                        pass

                entry = {
                    "url": getattr(res, "url", url),
                    "title": getattr(res, "title", None),
                    "html": html,
                    "markdown": markdown,
                    "links": getattr(res, "links", []),
                    "status_code": getattr(res, "status_code", None),
                    "success": getattr(res, "success", True),
                    "skip_ingest": skip_ingest,
                }

                if paywall_meta is not None:
                    entry["paywall"] = {
                        "is_paywall": getattr(paywall_meta, "is_paywall", False),
                        "confidence": float(getattr(paywall_meta, "confidence", 0.0)),
                        "reasons": getattr(paywall_meta, "reasons", []),
                    }

                results.append(entry)
        except Exception as exc:
            results.append({"url": url, "error": str(exc), "success": False})

    return {"results": results}
