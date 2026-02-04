"""Crawl4AI adapter used by the unified crawler engine.

The crawler engine delegates to this module when a profile explicitly requests
Crawl4AI-backed crawling.  The adapter translates profile dictionaries into
``crawl4ai`` configuration objects and converts the resulting pages back into
articles using the existing extraction pipeline so downstream ingestion logic
remains unchanged.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from urllib.parse import urljoin, urlparse

from agents.sites.generic_site_crawler import GenericSiteCrawler, SiteConfig
from common.json_utils import make_json_safe
from common.observability import get_logger

try:  # Metrics are optional; crawler operates without Prometheus stack.
    from common.metrics import get_metrics
except ImportError:  # pragma: no cover - metrics disabled in some environments
    get_metrics = None  # type: ignore

logger = get_logger(__name__)

try:  # Optional dependency, resolved at runtime when available
    crawl4ai = importlib.import_module("crawl4ai")  # type: ignore
except ImportError:  # pragma: no cover - missing optional dependency
    crawl4ai = None  # type: ignore

# Narrow allow-lists keep the translated run configuration maintainable and
# avoid surprising ``crawl4ai`` keyword errors when new options are introduced.
_ALLOWED_BROWSER_KEYS = {
    "browser_type",
    "headless",
    "viewport_width",
    "viewport_height",
    "user_agent",
    "user_agent_mode",
    "proxy",
    "cookies",
    "headers",
    "text_mode",
    "verbose",
    "extra_args",
    "ignore_https_errors",
}

_ALLOWED_RUN_CONFIG_KEYS = {
    "word_count_threshold",
    "exclude_external_links",
    "remove_overlay_elements",
    "process_iframes",
    "target_elements",
    "excluded_tags",
    "only_text",
    "score_links",
    "wait_for",
    "wait_for_timeout",
    "js_code",
    "screenshot",
    "pdf",
    "capture_mhtml",
    "exclude_all_images",
    "exclude_external_images",
    "image_score_threshold",
    "table_score_threshold",
}

_ALLOWED_LINK_PREVIEW_KEYS = {
    "include_internal",
    "include_external",
    "include_patterns",
    "exclude_patterns",
    "max_links",
    "concurrency",
    "timeout",
    "query",
    "score_threshold",
    "verbose",
}


@dataclass
class CrawlContext:
    site_config: SiteConfig
    profile: dict[str, Any]
    max_articles: int
    follow_internal_links: bool
    page_budget: int
    # If True the crawler is allowed to follow links outside the configured
    # site domain(s). When False we explicitly prevent following links whose
    # network location (netloc) does not match the site's domain or its
    # configured alternate domains.
    follow_external: bool = False


def _ensure_absolute(url: str, base: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    return urljoin(base, url)


def _normalise_url_for_site(url: str, site_config: SiteConfig) -> str:
    if not url:
        return ""
    base = (
        site_config.start_url or f"https://{site_config.domain}"
        if site_config.domain
        else ""
    )
    if not base:
        return url
    return _ensure_absolute(url, base)


def _build_browser_config(settings: dict[str, Any] | None):
    if not settings:
        return None
    if crawl4ai is None:  # pragma: no cover - optional dependency missing
        return None

    BrowserConfig = getattr(crawl4ai, "BrowserConfig", None)
    if BrowserConfig is None:
        return None

    kwargs = {key: settings[key] for key in _ALLOWED_BROWSER_KEYS if key in settings}
    if not kwargs:
        return None
    return BrowserConfig(**kwargs)


def _build_link_preview_config(settings: dict[str, Any] | None):
    if not settings:
        return None

    LinkPreviewConfig = None
    if crawl4ai is not None:
        LinkPreviewConfig = getattr(crawl4ai, "LinkPreviewConfig", None)
        if LinkPreviewConfig is None:
            try:
                adaptive = importlib.import_module("crawl4ai.adaptive_crawler")
                LinkPreviewConfig = getattr(adaptive, "LinkPreviewConfig", None)
            except ImportError:  # pragma: no cover - optional
                LinkPreviewConfig = None
    if LinkPreviewConfig is None:
        return None

    kwargs = {
        key: settings[key] for key in _ALLOWED_LINK_PREVIEW_KEYS if key in settings
    }
    if not kwargs:
        return None
    for pattern_key in ("include_patterns", "exclude_patterns"):
        if pattern_key in kwargs and isinstance(kwargs[pattern_key], str):
            kwargs[pattern_key] = [kwargs[pattern_key]]
    return LinkPreviewConfig(**kwargs)


def _build_run_config(profile: dict[str, Any]):
    run_config_def: dict[str, Any] = dict(profile.get("run_config") or {})
    if profile.get("wait_for") and "wait_for" not in run_config_def:
        run_config_def["wait_for"] = profile["wait_for"]
    if profile.get("js_code") and "js_code" not in run_config_def:
        run_config_def["js_code"] = profile["js_code"]

    markdown_generator_def = None
    if "markdown_generator" in run_config_def:
        markdown_generator_def = run_config_def.pop("markdown_generator")

    kwargs = {
        key: run_config_def[key]
        for key in _ALLOWED_RUN_CONFIG_KEYS
        if key in run_config_def
    }

    for list_key in ("js_code", "target_elements", "excluded_tags"):
        if list_key in kwargs and isinstance(kwargs[list_key], str):
            kwargs[list_key] = [kwargs[list_key]]

    link_preview_cfg = _build_link_preview_config(profile.get("link_preview"))
    if link_preview_cfg:
        kwargs["link_preview_config"] = link_preview_cfg

    if markdown_generator_def:
        generator = _build_markdown_generator(markdown_generator_def)
        if generator is not None:
            kwargs["markdown_generator"] = generator

    adaptive_kwargs = profile.get("adaptive") or {}

    if crawl4ai is None:  # pragma: no cover - surfaced to caller fallback
        raise ImportError("crawl4ai is not installed")

    CacheMode = getattr(crawl4ai, "CacheMode", None)
    CrawlerRunConfig = getattr(crawl4ai, "CrawlerRunConfig", None)
    AdaptiveConfig = getattr(crawl4ai, "AdaptiveConfig", None)
    if CacheMode is None or CrawlerRunConfig is None:
        raise ImportError("crawl4ai CacheMode or CrawlerRunConfig missing")

    cache_mode = profile.get("run_config", {}).get("cache_mode", "bypass")
    cache_mode_enum = getattr(CacheMode, str(cache_mode).upper(), CacheMode.BYPASS)

    config = CrawlerRunConfig(cache_mode=cache_mode_enum, **kwargs)

    if AdaptiveConfig is not None and adaptive_kwargs:
        try:
            adaptive_config = AdaptiveConfig(**adaptive_kwargs)
        except TypeError:
            adaptive_config = None
        if adaptive_config is not None:
            config.adaptive_config = adaptive_config  # type: ignore[attr-defined]

    return config


def _build_content_filter(settings: Mapping[str, Any] | None):
    if not settings:
        return None
    if crawl4ai is None:
        return None

    try:
        content_mod = importlib.import_module("crawl4ai.content_filter_strategy")
        BM25ContentFilter = getattr(content_mod, "BM25ContentFilter", None)
        PruningContentFilter = getattr(content_mod, "PruningContentFilter", None)
    except ImportError:  # pragma: no cover - optional dependency missing
        return None

    filter_type = str(settings.get("type", "")).strip().lower()
    options = dict(settings)
    options.pop("type", None)

    if filter_type in {"bm25", "bm25contentfilter"} and BM25ContentFilter is not None:
        return BM25ContentFilter(**options)
    if (
        filter_type in {"pruning", "pruningcontentfilter"}
        and PruningContentFilter is not None
    ):
        return PruningContentFilter(**options)
    return None


def _build_markdown_generator(settings: Mapping[str, Any] | None):
    if not settings:
        return None
    if crawl4ai is None:
        return None

    DefaultMarkdownGenerator = getattr(crawl4ai, "DefaultMarkdownGenerator", None)
    if DefaultMarkdownGenerator is None:
        try:
            markdown_module = importlib.import_module(
                "crawl4ai.markdown_generation_strategy"
            )
            DefaultMarkdownGenerator = getattr(
                markdown_module, "DefaultMarkdownGenerator", None
            )
        except ImportError:  # pragma: no cover - optional dependency missing
            DefaultMarkdownGenerator = None
    if DefaultMarkdownGenerator is None:
        return None

    kwargs: dict[str, Any] = {}
    content_filter = _build_content_filter(
        settings.get("content_filter") if isinstance(settings, Mapping) else None
    )
    if content_filter is not None:
        kwargs["content_filter"] = content_filter
    return DefaultMarkdownGenerator(**kwargs)


def _select_link_candidates(
    links: Sequence[dict[str, Any]],
    context: CrawlContext,
    visited: set[str],
    remaining_budget: int,
) -> list[str]:
    if not links or remaining_budget <= 0:
        return []

    include_patterns = (
        context.profile.get("link_preview", {}).get("include_patterns") or []
    )
    exclude_patterns = (
        context.profile.get("link_preview", {}).get("exclude_patterns") or []
    )
    include_patterns = (
        include_patterns if isinstance(include_patterns, list) else [include_patterns]
    )
    exclude_patterns = (
        exclude_patterns if isinstance(exclude_patterns, list) else [exclude_patterns]
    )
    require_article_like = bool(
        (context.profile.get("extra") or {}).get("require_article_like_url")
    )

    def _score(entry: dict[str, Any]) -> float:
        for key in ("total_score", "contextual_score", "intrinsic_score"):
            value = entry.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    allowed_domains: set[str] = set()
    if context.site_config.domain:
        allowed_domains.add(str(context.site_config.domain).lower())
    for url in context.profile.get("start_urls", []) or []:
        parsed = urlparse(str(url))
        if parsed.netloc:
            allowed_domains.add(parsed.netloc.lower())

    extra_domains = (context.profile.get("extra") or {}).get("alternate_domains")
    if extra_domains:
        if isinstance(extra_domains, str):
            allowed_domains.add(extra_domains.lower())
        else:
            allowed_domains.update(str(item).lower() for item in extra_domains if item)

    filtered: list[tuple[float, str]] = []

    def _is_allowed_domain(netloc: str) -> bool:
        if not netloc:
            return False
        nl = netloc.lower()
        for domain in allowed_domains:
            d = domain.lower()
            if nl == d or nl.endswith("." + d):
                return True
        return False

    for item in links:
        href = item.get("href")
        if not href:
            continue
        absolute = _normalise_url_for_site(href, context.site_config)
        if not absolute or absolute in visited:
            continue
        parsed = urlparse(absolute)
        netloc = parsed.netloc.lower()
        # If caller asked to avoid following external links, only allow
        # candidates whose netloc clearly matches one of the allowed domains
        # (supporting exact match and subdomains). If allowed_domains is empty
        # fall back to the site's start_url host if present.
        if not context.follow_external:
            if allowed_domains:
                if netloc and not _is_allowed_domain(netloc):
                    continue
            else:
                base_netloc = urlparse(
                    context.site_config.start_url or ""
                ).netloc.lower()
                if (
                    netloc
                    and base_netloc
                    and netloc != base_netloc
                    and not netloc.endswith("." + base_netloc)
                ):
                    continue
        if include_patterns and not any(
            pattern in absolute for pattern in include_patterns
        ):
            continue
        if exclude_patterns and any(
            pattern in absolute for pattern in exclude_patterns
        ):
            continue
        if require_article_like:
            path = parsed.path.lower()
            if not ("/articles/" in path or re.search(r"-\d{4,}", path)):
                continue
        filtered.append((_score(item), absolute))

    filtered.sort(key=lambda entry: entry[0], reverse=True)
    return [url for _, url in filtered[:remaining_budget]]


def _build_article_from_result(
    builder: GenericSiteCrawler,
    target_url: str,
    result: Any,
    profile: dict[str, Any],
    links_followed: int,
) -> dict[str, Any] | None:
    html = getattr(result, "cleaned_html", None) or getattr(result, "html", None)
    if not html:
        markdown_obj = getattr(result, "markdown", None)
        raw_markdown = (
            getattr(markdown_obj, "raw_markdown", None) if markdown_obj else None
        )
        if raw_markdown:
            html = f"<article>{raw_markdown}</article>"
    if not html:
        return None

    article = builder._build_article(target_url, html)
    if not article:
        return None

    metadata = article.setdefault("extraction_metadata", {})
    crawl_meta = metadata.setdefault("crawl4ai", {})
    crawl_meta.update(
        {
            "profile_slug": profile.get("profile_slug"),
            "mode": profile.get("mode"),
            "source_url": getattr(result, "url", target_url),
            "links_followed": links_followed,
            "link_preview_count": len(getattr(result, "links", {}).get("internal", []))
            if getattr(result, "links", None)
            else 0,
        }
    )

    adaptive_settings = profile.get("adaptive") or {}
    if adaptive_settings:
        crawl_meta["adaptive_profile"] = make_json_safe(dict(adaptive_settings))

    profile_query = (profile.get("extra") or {}).get("query")
    if profile_query:
        hints = crawl_meta.setdefault("hints", {})
        hints["query"] = profile_query

    page_metadata = getattr(result, "metadata", None)
    if page_metadata:
        crawl_meta["page_metadata"] = make_json_safe(page_metadata)

    if (profile.get("extra") or {}).get("disable_dedupe"):
        article["disable_dedupe"] = True
    return article


def _build_article_from_adaptive_doc(
    builder: GenericSiteCrawler,
    doc: Mapping[str, Any],
    profile: dict[str, Any],
    adaptive: Any,
    state: Any,
) -> dict[str, Any] | None:
    target_url = str(doc.get("url") or "").strip()

    html = doc.get("cleaned_html") or doc.get("html") or doc.get("raw_html")
    markdown_content = doc.get("content")
    markdown_ns: SimpleNamespace | None = None
    if not html and markdown_content:
        html = f"<article>{markdown_content}</article>"
    if markdown_content:
        markdown_ns = SimpleNamespace(raw_markdown=markdown_content)

    if not html and not markdown_ns:
        return None

    result = SimpleNamespace(
        cleaned_html=html,
        markdown=markdown_ns,
        url=target_url,
        metadata=doc.get("metadata"),
        links=doc.get("links"),
    )

    links_followed = len(getattr(state, "crawled_urls", []) or [])
    article = _build_article_from_result(
        builder,
        target_url or getattr(state, "start_url", ""),
        result,
        profile,
        links_followed=links_followed,
    )
    if not article:
        return None

    crawl_meta = article.setdefault("extraction_metadata", {}).setdefault(
        "crawl4ai", {}
    )
    adaptive_run = crawl_meta.setdefault("adaptive_run", {})
    confidence = getattr(adaptive, "confidence", None)
    if confidence is not None:
        adaptive_run["confidence"] = float(confidence)
    coverage_stats = getattr(adaptive, "coverage_stats", None)
    if coverage_stats:
        adaptive_run["coverage_stats"] = make_json_safe(dict(coverage_stats))
    if hasattr(adaptive, "is_sufficient"):
        adaptive_run["is_sufficient"] = bool(adaptive.is_sufficient)
    pages_crawled = len(getattr(state, "crawled_urls", []) or [])
    if pages_crawled:
        adaptive_run["pages_crawled"] = pages_crawled
    stop_reason = getattr(state, "stop_reason", None)
    if stop_reason:
        adaptive_run["stop_reason"] = stop_reason
    score = doc.get("score")
    if score is not None:
        adaptive_run["source_score"] = score

    return article


def _record_adaptive_metrics(
    adaptive: Any,
    state: Any,
    emitted_count: int,
    profile: Mapping[str, Any] | None,
) -> None:
    """Push adaptive crawl telemetry into the metrics store."""
    if get_metrics is None:
        return

    try:
        metrics = get_metrics("crawler")
    except Exception:  # pragma: no cover - metrics backend unavailable
        return

    try:
        metrics.increment("adaptive_runs_total")

        metrics.gauge("adaptive_articles_emitted", float(max(0, emitted_count)))

        confidence = getattr(adaptive, "confidence", None)
        if confidence is not None:
            metrics.gauge("adaptive_confidence", float(confidence))

        is_sufficient = getattr(adaptive, "is_sufficient", None)
        if is_sufficient is not None:
            metrics.gauge("adaptive_is_sufficient", 1.0 if bool(is_sufficient) else 0.0)

        pages_crawled = 0
        stop_reason = None
        if state is not None:
            crawled_urls = getattr(state, "crawled_urls", []) or []
            try:
                pages_crawled = len(crawled_urls)
            except TypeError:
                pages_crawled = 0
            stop_reason = getattr(state, "stop_reason", None)

        metrics.gauge("adaptive_pages_crawled", float(pages_crawled))

        if stop_reason:
            metrics.increment(f"adaptive_stop_reason_{stop_reason}")

        coverage_stats = getattr(adaptive, "coverage_stats", None)
        if isinstance(coverage_stats, Mapping):
            for key, value in coverage_stats.items():
                try:
                    metrics.gauge(f"adaptive_coverage_{key}", float(value))
                except (TypeError, ValueError):
                    continue

        profile_slug = (profile or {}).get("profile_slug") if profile else None
        if profile_slug:
            metrics.increment(f"adaptive_profile_runs_{profile_slug}")

    except Exception as exc:  # pragma: no cover - metrics should not break crawl
        logger.debug("Adaptive metrics recording failed: %s", exc)


async def _run_adaptive_crawl(
    async_webcrawler_cls: Any,
    browser_config: Any,
    run_config: Any,
    adaptive_config: Any,
    start_urls: Sequence[str],
    query: str,
    builder: GenericSiteCrawler,
    profile: dict[str, Any],
    max_articles: int,
) -> list[dict[str, Any]]:
    AdaptiveCrawler = getattr(crawl4ai, "AdaptiveCrawler", None)
    if AdaptiveCrawler is None:
        return []

    articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    crawler_args = {}
    if browser_config is not None:
        crawler_args["config"] = browser_config

    async with async_webcrawler_cls(**crawler_args) as crawler:
        for url in start_urls:
            if len(articles) >= max_articles:
                break
            url = str(url or "").strip()
            if not url:
                continue
            adaptive = None
            state = None
            emitted_before = len(articles)
            try:
                try:
                    adaptive = AdaptiveCrawler(crawler, config=adaptive_config)
                except TypeError:  # pragma: no cover - older signatures
                    adaptive = AdaptiveCrawler(crawler, adaptive_config)

                current_run_config = run_config
                if hasattr(run_config, "clone"):
                    try:
                        current_run_config = run_config.clone()
                    except Exception:  # pragma: no cover - defensive
                        current_run_config = run_config

                try:
                    state = await adaptive.digest(
                        url, query, run_config=current_run_config
                    )
                except TypeError:
                    state = await adaptive.digest(url, query)
            except Exception as exc:  # noqa: BLE001 - prefer resilience
                logger.warning("Adaptive crawl failed for %s: %s", url, exc)
                continue

            remaining = max_articles - len(articles)
            if remaining <= 0:
                break

            docs = []
            if hasattr(adaptive, "get_relevant_content"):
                try:
                    docs = adaptive.get_relevant_content(top_k=remaining) or []
                except Exception:  # pragma: no cover - best effort fallback
                    docs = []

            for doc in docs:
                doc_url = str(doc.get("url") or "").strip()
                if doc_url and doc_url in seen_urls:
                    continue
                article = _build_article_from_adaptive_doc(
                    builder, doc, profile, adaptive, state
                )
                if article:
                    seen_urls.add(article.get("url") or doc_url)
                    articles.append(article)
                if len(articles) >= max_articles:
                    break

            _record_adaptive_metrics(
                adaptive, state, len(articles) - emitted_before, profile
            )

    return articles


async def crawl_site_with_crawl4ai(
    site_config: SiteConfig,
    profile: dict[str, Any],
    max_articles: int,
    *,
    follow_external: bool | None = None,
) -> list[dict[str, Any]]:
    """Execute a Crawl4AI-backed crawl using the provided profile."""
    if crawl4ai is None:  # pragma: no cover - handled by caller fallback
        raise ImportError("crawl4ai is not installed")

    AsyncWebCrawler = getattr(crawl4ai, "AsyncWebCrawler", None)
    if AsyncWebCrawler is None:
        raise ImportError("crawl4ai AsyncWebCrawler not available")

    article_limit = max(1, int(max_articles or 1))
    browser_config = _build_browser_config(profile.get("browser_config"))
    run_config = _build_run_config(profile)

    start_urls = profile.get("start_urls") or []
    if not start_urls:
        inferred = site_config.start_url
        if inferred:
            start_urls = [inferred]
    if not start_urls:
        logger.warning(
            "Crawl4AI profile for %s did not provide any start URLs", site_config.name
        )
        return []

    unique_urls: list[str] = []
    for candidate in start_urls:
        normalised = _normalise_url_for_site(str(candidate), site_config)
        if normalised and normalised not in unique_urls:
            unique_urls.append(normalised)

    if not unique_urls:
        return []

    follow_internal_links = bool(profile.get("follow_internal_links", True))
    # Determine whether we are allowed to follow links outside the target
    # domain(s). Priority order:
    # 1. explicit function parameter `follow_external` if not None
    # 2. profile-level override `profile['follow_external']` if present
    # 3. environment variable CRAWL4AI_FOLLOW_EXTERNAL (default: false)
    if follow_external is None:
        if "follow_external" in profile:
            follow_external = bool(profile.get("follow_external"))
        else:
            follow_external = os.getenv(
                "CRAWL4AI_FOLLOW_EXTERNAL", "false"
            ).lower() in ("1", "true", "yes")
    page_budget = int(profile.get("max_pages") or article_limit or len(unique_urls))
    page_budget = max(page_budget, len(unique_urls))
    seed_urls = set(unique_urls)
    extra_config = profile.get("extra") or {}
    skip_seed_articles = bool(extra_config.get("skip_seed_articles"))
    strict_skip_seed_articles = bool(extra_config.get("strict_skip_seed_articles"))
    context = CrawlContext(
        site_config=site_config,
        profile=profile,
        max_articles=article_limit,
        follow_internal_links=follow_internal_links,
        page_budget=page_budget,
        follow_external=bool(follow_external),
    )

    builder = GenericSiteCrawler(site_config, enable_http_fetch=False)
    articles: list[dict[str, Any]] = []
    seed_buffer: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue: list[str] = list(unique_urls)
    pages_fetched = 0

    adaptive_config = getattr(run_config, "adaptive_config", None)
    profile_query = (profile.get("extra") or {}).get("query")
    if adaptive_config is not None and profile_query:
        adaptive_articles = await _run_adaptive_crawl(
            AsyncWebCrawler,
            browser_config,
            run_config,
            adaptive_config,
            unique_urls,
            profile_query,
            builder,
            profile,
            context.max_articles,
        )
        if adaptive_articles:
            return adaptive_articles[: context.max_articles]

    recoverable_markers = (
        "browsercontext.new_page",
        "connection closed while reading from the driver",
        "pipe closed by peer",
    )

    def _is_recoverable_error(message: str | None) -> bool:
        if not message:
            return False
        lower = message.lower()
        return any(marker in lower for marker in recoverable_markers)

    async def _fetch_with_retries(target_url: str):
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                crawler_factory = (
                    AsyncWebCrawler(config=browser_config)
                    if browser_config
                    else AsyncWebCrawler()
                )
                async with crawler_factory as crawler:
                    result = await crawler.arun(target_url, config=run_config)
            except Exception as exc:  # noqa: BLE001 - robustness first
                message = str(exc)
                logger.warning(
                    "Crawl4AI failed for %s (attempt %s/%s): %s",
                    target_url,
                    attempt,
                    attempts,
                    message,
                )
                if attempt == attempts or not _is_recoverable_error(message):
                    return None
                await asyncio.sleep(0.5 * attempt)
                continue

            if getattr(result, "success", True):
                return result

            error_text = str(
                getattr(result, "error", "") or getattr(result, "message", "")
            )
            logger.debug("Crawl4AI returned unsuccessful result for %s", target_url)
            if attempt == attempts or not _is_recoverable_error(error_text):
                return result
            await asyncio.sleep(0.5 * attempt)

        return None

    while (
        queue
        and pages_fetched < context.page_budget
        and len(articles) < context.max_articles
    ):
        current_url = queue.pop(0)
        if not current_url or current_url in visited:
            continue
        visited.add(current_url)

        result = await _fetch_with_retries(current_url)
        if result is None:
            continue

        pages_fetched += 1
        if not getattr(result, "success", True):
            continue

        article = _build_article_from_result(
            builder,
            current_url,
            result,
            profile,
            links_followed=max(0, len(visited) - len(unique_urls)),
        )
        if article:
            if skip_seed_articles and current_url in seed_urls:
                seed_buffer.append(article)
            else:
                articles.append(article)
                if len(articles) >= context.max_articles:
                    break

        if (
            context.follow_internal_links
            and len(articles) < context.max_articles
            and getattr(result, "links", None)
        ):
            remaining_pages = context.page_budget - pages_fetched
            candidates = result.links.get("internal", []) if result.links else []
            next_urls = _select_link_candidates(
                candidates, context, visited, remaining_pages
            )
            for url in next_urls:
                if url not in queue and url not in visited:
                    queue.append(url)

    if (
        skip_seed_articles
        and not strict_skip_seed_articles
        and len(articles) < context.max_articles
    ):
        needed = context.max_articles - len(articles)
        articles.extend(seed_buffer[:needed])

    return articles[: context.max_articles]
