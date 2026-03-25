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
import json
import os
import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from urllib.parse import urljoin, urlparse

from agents.common.triage_adapter import TriageAdapter
from agents.sites.generic_site_crawler import GenericSiteCrawler, SiteConfig
from common.json_utils import make_json_safe
from common.observability import get_logger

try:  # Metrics are optional; crawler operates without Prometheus stack.
    from common.metrics import get_metrics
except ImportError:  # pragma: no cover - metrics disabled in some environments
    get_metrics = None  # type: ignore

logger = get_logger(__name__)

_TRIAGE_ADAPTER = TriageAdapter(name="crawler_ingestion_triage")


_NON_NEWS_URL_RE = re.compile(
    r"/(contact|about|mission|corporate|careers|jobs|privacy|terms|cookies|help|support|faq|about-us|company)(/|$)",
    re.IGNORECASE,
)
_INDEX_URL_RE = re.compile(
    r"/(category|categories|tag|tags|topic|topics|section|sections|latest|most-read|editorial|opinion)(/|$)",
    re.IGNORECASE,
)
_OVERLAY_TEXT_RE = re.compile(
    r"cookie|consent|accept all|reject all|privacy settings|manage preferences|sign in|subscribe",
    re.IGNORECASE,
)
_NAV_TEXT_RE = re.compile(
    r"home\s+news|editor'?s picks|most read|top stories|latest news|breaking news|newsletter|advertis",
    re.IGNORECASE,
)


@dataclass
class IngestionTriageDecision:
    decision: str
    confidence: float
    reason_codes: list[str]
    source: str
    page_type: str | None = None


def _triage_enabled() -> bool:
    return _env_bool("CRAWL4AI_INGESTION_TRIAGE_ENABLED", default=False)


def _ai_triage_enabled() -> bool:
    return _env_bool("CRAWL4AI_AI_TRIAGE_ENABLED", default=False)


def _ai_triage_ambiguous_only() -> bool:
    return _env_bool("CRAWL4AI_AI_TRIAGE_AMBIGUOUS_ONLY", default=True)


def _ai_triage_reject_confidence() -> float:
    raw = os.environ.get("CRAWL4AI_AI_TRIAGE_REJECT_CONFIDENCE", "0.78")
    try:
        return min(1.0, max(0.0, float(raw)))
    except (TypeError, ValueError):
        return 0.78


def _ai_triage_domain_thresholds() -> dict[str, float]:
    raw = os.environ.get("CRAWL4AI_AI_TRIAGE_DOMAIN_THRESHOLDS_JSON", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("Invalid CRAWL4AI_AI_TRIAGE_DOMAIN_THRESHOLDS_JSON value")
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in parsed.items():
        domain = str(key or "").strip().lower()
        if not domain:
            continue
        try:
            threshold = min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            continue
        out[domain] = threshold
    return out


def _ai_triage_reject_confidence_for_domain(domain: str | None) -> float:
    base = _ai_triage_reject_confidence()
    if not domain:
        return base
    d = str(domain).strip().lower()
    if not d:
        return base
    thresholds = _ai_triage_domain_thresholds()
    if d in thresholds:
        return thresholds[d]
    # Suffix match for subdomains, preferring the longest key.
    matched: list[tuple[int, float]] = []
    for candidate, threshold in thresholds.items():
        if d == candidate or d.endswith("." + candidate):
            matched.append((len(candidate), threshold))
    if not matched:
        return base
    matched.sort(key=lambda item: item[0], reverse=True)
    return matched[0][1]


def _record_triage_metrics(
    decision: IngestionTriageDecision,
    site_config: SiteConfig,
) -> None:
    if get_metrics is None:
        return
    try:
        metrics = get_metrics("crawler")
    except Exception:
        return

    domain = (site_config.domain or "unknown").strip().lower() or "unknown"
    safe_domain = re.sub(r"[^a-z0-9_]+", "_", domain)
    source = (decision.source or "unknown").strip().lower() or "unknown"
    final_decision = (decision.decision or "unknown").strip().lower() or "unknown"

    metrics.increment(f"triage_decision_{final_decision}_total")
    metrics.increment(f"triage_source_{source}_total")
    metrics.increment(f"triage_domain_{safe_domain}_{final_decision}_total")
    metrics.gauge("triage_last_confidence", float(decision.confidence))

    for code in decision.reason_codes[:5]:
        safe = re.sub(r"[^a-z0-9_]+", "_", str(code).strip().lower())
        if not safe:
            continue
        metrics.increment(f"triage_reason_{safe}_total")


def _heuristic_triage_decision(url: str, title: str, content: str) -> IngestionTriageDecision:
    text = content or ""
    text_l = text.lower()
    word_count = len(text.split())
    overlay_hits = len(_OVERLAY_TEXT_RE.findall(text_l))
    nav_hits = len(_NAV_TEXT_RE.findall(text_l))
    reason_codes: list[str] = []

    parsed = urlparse(url or "")
    path = (parsed.path or "").lower()

    if _NON_NEWS_URL_RE.search(path):
        reason_codes.append("non_news_utility_url")
    if _INDEX_URL_RE.search(path):
        reason_codes.append("index_or_navigation_url")
    if overlay_hits >= 3:
        reason_codes.append("overlay_heavy_text")
    if nav_hits >= 4:
        reason_codes.append("navigation_heavy_text")
    if word_count < 80:
        reason_codes.append("insufficient_article_length")

    # Deterministic hard reject for clear non-news utility pages.
    if "non_news_utility_url" in reason_codes:
        return IngestionTriageDecision(
            decision="reject",
            confidence=0.98,
            reason_codes=reason_codes,
            source="heuristic",
            page_type="utility",
        )

    # Deterministic reject for clear index/overlay pages with low narrative density.
    if (
        "index_or_navigation_url" in reason_codes
        and (overlay_hits >= 2 or nav_hits >= 5)
        and word_count < 700
    ):
        return IngestionTriageDecision(
            decision="reject",
            confidence=0.9,
            reason_codes=reason_codes,
            source="heuristic",
            page_type="index",
        )

    # Clear accept path for article-like long-form content.
    article_cues = bool(
        re.search(r"\b(published|updated|by\s+[A-Z][a-z]+|according to)\b", text)
    )
    if word_count >= 220 and overlay_hits <= 1 and nav_hits <= 2 and (article_cues or len(title) > 20):
        return IngestionTriageDecision(
            decision="accept",
            confidence=0.85,
            reason_codes=["article_like_content"],
            source="heuristic",
            page_type="article",
        )

    return IngestionTriageDecision(
        decision="ambiguous",
        confidence=0.5,
        reason_codes=reason_codes or ["ambiguous_page_shape"],
        source="heuristic",
        page_type=None,
    )


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    clean = text.replace("```json", "```").strip()
    if clean.startswith("```") and clean.endswith("```"):
        clean = clean[3:-3].strip()
    try:
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        match = re.search(r"\{[\s\S]*\}", clean)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None


def _triage_training_enabled() -> bool:
    return _env_bool("CRAWL4AI_TRIAGE_TRAINING_FEEDBACK_ENABLED", default=False)


def _triage_training_sample_rate() -> float:
    raw = os.environ.get("CRAWL4AI_TRIAGE_TRAINING_SAMPLE_RATE", "1.0")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0
    return min(1.0, max(0.0, value))


def _forward_triage_prediction_for_training(
    *,
    url: str,
    title: str,
    content: str,
    decision: IngestionTriageDecision,
) -> None:
    if not _triage_training_enabled():
        return
    if random.random() > _triage_training_sample_rate():
        return

    snippet = (content or "")[:1200]
    training_input = f"URL: {url}\nTitle: {title}\nContent snippet:\n{snippet}"
    prediction_payload = {
        "decision": decision.decision,
        "reason_codes": list(decision.reason_codes),
        "source": decision.source,
        "page_type": decision.page_type,
    }
    training_agent = (
        os.environ.get("CRAWL4AI_TRIAGE_TRAINING_AGENT", "crawler_triage").strip()
        or "crawler_triage"
    )

    try:
        from training_system.core.system_manager import collect_prediction

        collect_prediction(
            agent_name=training_agent,
            task_type="ingestion_triage",
            input_text=training_input,
            prediction=prediction_payload,
            confidence=float(decision.confidence),
            ground_truth=None,
            source_url=url,
        )
    except Exception as exc:
        logger.debug("Failed to forward triage prediction for training: %s", exc)


def _run_ai_triage(url: str, title: str, content: str) -> IngestionTriageDecision | None:
    parsed = _TRIAGE_ADAPTER.classify_page(url=url, title=title, content=content)
    if not isinstance(parsed, dict):
        return None

    decision = str(parsed.get("decision") or "").strip().lower()
    if decision not in {"accept", "reject", "quarantine"}:
        return None
    try:
        confidence = float(parsed.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = min(1.0, max(0.0, confidence))
    reason_codes = [
        str(item).strip().lower().replace(" ", "_")
        for item in (parsed.get("reason_codes") or [])
        if str(item).strip()
    ]
    return IngestionTriageDecision(
        decision=decision,
        confidence=confidence,
        reason_codes=reason_codes or ["ai_triage_no_reason"],
        source="ai",
        page_type=str(parsed.get("page_type") or "").strip().lower() or None,
    )


async def _apply_ingestion_triage(
    article: dict[str, Any],
    site_config: SiteConfig,
    profile: dict[str, Any],
) -> dict[str, Any]:
    if not _triage_enabled():
        return article

    url = str(article.get("url") or "")
    title = str(article.get("title") or "")
    content = str(article.get("content") or article.get("extracted_text") or "")
    if not content:
        return article

    heuristic = _heuristic_triage_decision(url=url, title=title, content=content)
    final_decision = heuristic

    if _ai_triage_enabled():
        should_call_ai = (not _ai_triage_ambiguous_only()) or heuristic.decision == "ambiguous"
        if should_call_ai:
            ai_decision = await asyncio.to_thread(_run_ai_triage, url, title, content)
            if ai_decision is not None:
                reject_threshold = _ai_triage_reject_confidence_for_domain(
                    site_config.domain
                )
                if ai_decision.decision == "accept":
                    final_decision = ai_decision
                elif ai_decision.decision in {"reject", "quarantine"}:
                    if ai_decision.confidence >= reject_threshold:
                        final_decision = ai_decision
                elif heuristic.decision == "ambiguous":
                    final_decision = ai_decision

    metadata = article.setdefault("extraction_metadata", {})
    triage_meta = metadata.setdefault("ingestion_triage", {})
    triage_meta.update(
        {
            "enabled": True,
            "decision": final_decision.decision,
            "confidence": float(final_decision.confidence),
            "reason_codes": list(final_decision.reason_codes),
            "source": final_decision.source,
            "page_type": final_decision.page_type,
            "domain": site_config.domain,
            "profile_slug": profile.get("profile_slug"),
            "reject_confidence_threshold": _ai_triage_reject_confidence_for_domain(
                site_config.domain
            ),
        }
    )

    _record_triage_metrics(final_decision, site_config)

    await asyncio.to_thread(
        _forward_triage_prediction_for_training,
        url=url,
        title=title,
        content=content,
        decision=final_decision,
    )

    if final_decision.decision in {"reject", "quarantine"}:
        article["skip_ingest"] = True
        article["ingestion_status"] = (
            "triage_quarantined"
            if final_decision.decision == "quarantine"
            else "triage_rejected"
        )
        article["skip_reason"] = "ingestion_triage"
        article["triage_reason"] = ",".join(final_decision.reason_codes[:3])

    return article


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

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
    "exclude_social_media_links",
    "remove_overlay_elements",
    "process_iframes",
    "target_elements",
    "excluded_tags",
    "only_text",
    "check_robots_txt",
    "simulate_user",
    "scan_full_page",
    "mean_delay",
    "max_range",
    "semaphore_count",
    "page_timeout",
    "delay_before_return_html",
    "wait_until",
    "shared_data",
    "js_only",
    "extraction_strategy",
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
    "magic",
    "log_console",
    "keep_data_attributes",
    "override_navigator",
    "ignore_body_visibility",
    "prettiify",
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
    crawl_depth: int | None = None
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

    # Dynamic-site hooks: allow pre/post navigation JS snippets via profile extra.
    extra = profile.get("extra") or {}
    pre_nav_js = extra.get("pre_nav_js")
    post_nav_js = extra.get("post_nav_js")
    if pre_nav_js or post_nav_js:
        merged_js: list[str] = []
        existing_js = kwargs.get("js_code")
        if isinstance(existing_js, list):
            merged_js.extend(str(item) for item in existing_js if str(item).strip())
        elif isinstance(existing_js, str) and existing_js.strip():
            merged_js.append(existing_js)
        if pre_nav_js:
            merged_js.insert(0, str(pre_nav_js))
        if post_nav_js:
            merged_js.append(str(post_nav_js))
        kwargs["js_code"] = merged_js

    link_preview_cfg = _build_link_preview_config(profile.get("link_preview"))
    if link_preview_cfg:
        kwargs["link_preview_config"] = link_preview_cfg

    if markdown_generator_def:
        generator = _build_markdown_generator(markdown_generator_def)
        if generator is not None:
            kwargs["markdown_generator"] = generator

    extraction_def = run_config_def.get("extraction_strategy")
    if isinstance(extraction_def, Mapping):
        extraction_strategy = _build_extraction_strategy(extraction_def)
        if extraction_strategy is not None:
            kwargs["extraction_strategy"] = extraction_strategy
        elif "extraction_strategy" in kwargs:
            kwargs.pop("extraction_strategy", None)

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


def _build_extraction_strategy(settings: Mapping[str, Any] | None) -> Any | None:
    if not settings:
        return None
    if crawl4ai is None:
        return None

    strategy_type = str(settings.get("type") or "").strip().lower()
    options = {str(k): v for k, v in settings.items() if str(k) != "type"}
    if strategy_type in {"json_css", "jsoncssextractionstrategy"}:
        strategy_cls = getattr(crawl4ai, "JsonCssExtractionStrategy", None)
        if strategy_cls is None:
            try:
                strategy_mod = importlib.import_module("crawl4ai.extraction_strategy")
                strategy_cls = getattr(strategy_mod, "JsonCssExtractionStrategy", None)
            except ImportError:  # pragma: no cover
                strategy_cls = None
        if strategy_cls is None:
            return None
        try:
            return strategy_cls(**options)
        except Exception as exc:  # pragma: no cover - compatibility fallback
            logger.debug("Failed to initialize extraction strategy: %s", exc)
            return None

    return None


def _build_dispatcher(profile: dict[str, Any]) -> Any | None:
    """Build an optional Crawl4AI dispatcher object for batched crawling.

    The dispatcher API varies across Crawl4AI versions, so this helper keeps
    instantiation permissive and falls back to no dispatcher on errors.
    """
    if crawl4ai is None:
        return None

    dispatcher_def = profile.get("dispatcher")
    if not isinstance(dispatcher_def, Mapping):
        return None

    dispatcher_type = str(dispatcher_def.get("type") or "").strip().lower()
    dispatcher_kwargs = {
        str(k): v for k, v in dispatcher_def.items() if str(k) != "type"
    }
    if not dispatcher_type:
        return None

    aliases = {
        "memory": "MemoryAdaptiveDispatcher",
        "semaphore": "SemaphoreDispatcher",
    }

    candidate_names = [dispatcher_type]
    aliased = aliases.get(dispatcher_type)
    if aliased:
        candidate_names.append(aliased)
    if not dispatcher_type.endswith("dispatcher"):
        candidate_names.append(f"{dispatcher_type}_dispatcher")
        candidate_names.append(f"{dispatcher_type.title()}Dispatcher")

    for candidate in candidate_names:
        dispatcher_cls = getattr(crawl4ai, candidate, None)
        if dispatcher_cls is None:
            continue
        try:
            return dispatcher_cls(**dispatcher_kwargs)
        except Exception as exc:  # pragma: no cover - best-effort compatibility
            logger.debug("Failed to initialize dispatcher %s: %s", candidate, exc)
            continue

    return None


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
                    article = await _apply_ingestion_triage(
                        article,
                        builder.site_config,
                        profile,
                    )
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

    discovery_enabled = _env_bool("UNIFIED_CRAWLER_DISCOVERY_ENABLED", default=True)
    offsite_follow_enabled = _env_bool(
        "UNIFIED_CRAWLER_OFFSITE_FOLLOW_ENABLED", default=False
    )
    whitelist_only_mode = _env_bool("UNIFIED_CRAWLER_WHITELIST_ONLY_MODE", default=False)
    if whitelist_only_mode or not discovery_enabled or not offsite_follow_enabled:
        follow_external = False

    page_budget = int(profile.get("max_pages") or article_limit or len(unique_urls))
    page_budget = max(page_budget, len(unique_urls))
    configured_depth = (profile.get("extra") or {}).get("crawl_depth")
    crawl_depth: int | None = None
    if configured_depth is not None:
        try:
            crawl_depth = max(0, int(configured_depth))
        except (TypeError, ValueError):
            crawl_depth = None
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
        crawl_depth=crawl_depth,
        follow_external=bool(follow_external),
    )

    builder = GenericSiteCrawler(site_config, enable_http_fetch=False)
    articles: list[dict[str, Any]] = []
    seed_buffer: list[dict[str, Any]] = []
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(url, 0) for url in unique_urls]
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

    use_batch_seed_crawl = bool((profile.get("extra") or {}).get("use_arun_many"))
    if use_batch_seed_crawl and hasattr(AsyncWebCrawler, "arun_many"):
        crawler_factory = (
            AsyncWebCrawler(config=browser_config)
            if browser_config
            else AsyncWebCrawler()
        )
        dispatcher_obj = _build_dispatcher(profile)
        seed_targets = unique_urls[: context.page_budget]
        async with crawler_factory as crawler:
            try:
                if dispatcher_obj is not None:
                    results = await crawler.arun_many(
                        seed_targets,
                        config=run_config,
                        dispatcher=dispatcher_obj,
                    )
                else:
                    results = await crawler.arun_many(seed_targets, config=run_config)
            except TypeError:
                results = await crawler.arun_many(seed_targets, config=run_config)
            except Exception as exc:  # noqa: BLE001 - graceful fallback to queue mode
                logger.warning(
                    "Crawl4AI arun_many failed for %s: %s",
                    site_config.name,
                    exc,
                )
                results = []

        for target_url, result in zip(seed_targets, list(results or []), strict=False):
            if result is None or not getattr(result, "success", True):
                continue
            article = _build_article_from_result(
                builder,
                target_url,
                result,
                profile,
                links_followed=0,
            )
            if article:
                article = await _apply_ingestion_triage(article, site_config, profile)
                articles.append(article)
            if len(articles) >= context.max_articles:
                break

        if articles:
            return articles[: context.max_articles]

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

    async def _fetch_with_retries(crawler: Any, target_url: str) -> tuple[Any | None, bool]:
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
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
                if not _is_recoverable_error(message):
                    return None, False
                if attempt == attempts:
                    return None, True
                await asyncio.sleep(0.5 * attempt)
                continue

            if getattr(result, "success", True):
                return result, False

            error_text = str(
                getattr(result, "error", "") or getattr(result, "message", "")
            )
            logger.debug("Crawl4AI returned unsuccessful result for %s", target_url)
            if not _is_recoverable_error(error_text):
                return result, False
            if attempt == attempts:
                return result, True
            await asyncio.sleep(0.5 * attempt)

        return None, False

    while (
        queue
        and pages_fetched < context.page_budget
        and len(articles) < context.max_articles
    ):
        crawler_factory = (
            AsyncWebCrawler(config=browser_config)
            if browser_config
            else AsyncWebCrawler()
        )
        restart_session = False
        async with crawler_factory as crawler:
            while (
                queue
                and pages_fetched < context.page_budget
                and len(articles) < context.max_articles
            ):
                current_url, current_depth = queue.pop(0)
                if not current_url or current_url in visited:
                    continue

                result, restart_session = await _fetch_with_retries(crawler, current_url)
                if restart_session:
                    queue.insert(0, (current_url, current_depth))
                    logger.info(
                        "Restarting Crawl4AI browser session after recoverable driver/browser closure"
                    )
                    break

                visited.add(current_url)
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
                    article = await _apply_ingestion_triage(article, site_config, profile)
                    crawl_meta = article.setdefault("extraction_metadata", {}).setdefault(
                        "crawl4ai", {}
                    )
                    crawl_meta["crawl_depth"] = current_depth
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
                    if context.crawl_depth is not None and current_depth >= context.crawl_depth:
                        continue
                    remaining_pages = context.page_budget - pages_fetched
                    candidates = result.links.get("internal", []) if result.links else []
                    next_urls = _select_link_candidates(
                        candidates, context, visited, remaining_pages
                    )
                    for url in next_urls:
                        queued_urls = {queued for queued, _depth in queue}
                        if url not in queued_urls and url not in visited:
                            queue.append((url, current_depth + 1))

        if not restart_session:
            break

    if (
        skip_seed_articles
        and not strict_skip_seed_articles
        and len(articles) < context.max_articles
    ):
        needed = context.max_articles - len(articles)
        articles.extend(seed_buffer[:needed])

    return articles[: context.max_articles]
