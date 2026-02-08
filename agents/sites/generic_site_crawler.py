"""Lightweight generic crawler primitives used by the crawler agent.

The previous production implementation pulled in a large dependency tree that was
removed during the repository clean-up.  These stubs provide the minimum surface
area required by the crawler engine so the service can start successfully.  They
support simple HTTP fetching when explicitly enabled via environment variable
and fall back to no-op behaviour in offline environments.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

from agents.crawler.enhancements import (
    ModalHandler,
    ModalHandlingResult,
    PaywallDetector,
    ProxyManager,
    StealthBrowserFactory,
    UserAgentProvider,
)

try:  # readability-lxml (HTML → Article fallback)
    from lxml import html as lxml_html  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    lxml_html = None

from agents.crawler.extraction import ExtractionOutcome, extract_article_content
from common.observability import get_logger
from common.url_normalization import hash_article_url, normalize_article_url

logger = get_logger(__name__)


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    """Parse boolean-ish environment flags."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(init=False)
class SiteConfig:
    """Normalized site configuration wrapper used by crawler components."""

    source_id: int | None = None
    name: str = ""
    domain: str = ""
    url: str = ""
    crawling_strategy: str = "generic"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(self, source: Any):
        data = self._normalise_source(source)

        self.source_id = data.get("id")
        self.name = (
            data.get("name") or data.get("domain") or data.get("url") or "unknown"
        )

        raw_domain = data.get("domain")
        raw_url = data.get("url")

        if raw_domain:
            domain = raw_domain.strip()
        elif raw_url:
            parsed = urlparse(raw_url)
            domain = parsed.netloc or parsed.path
        else:
            domain = ""

        url = raw_url or ""

        if domain and "://" in domain:
            parsed = urlparse(domain)
            if parsed.netloc:
                if not url:
                    url = domain
                domain = parsed.netloc

        if not url and domain:
            scheme = "https" if not domain.startswith("http") else ""
            url = f"{scheme}://{domain}" if scheme else domain

        self.domain = domain
        self.url = url

        metadata = data.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        if not isinstance(metadata, Mapping):
            metadata = {}
        self.metadata = dict(metadata)

        self.crawling_strategy = (
            self.metadata.get("crawling_strategy")
            or data.get("crawling_strategy")
            or "generic"
        )

    @staticmethod
    def _normalise_source(source: Any) -> dict[str, Any]:
        if isinstance(source, SiteConfig):
            return source.to_dict()
        if isinstance(source, Mapping):
            return dict(source)
        if hasattr(source, "_mapping"):
            return dict(source._mapping)  # e.g. SQLAlchemy Row
        if hasattr(source, "_asdict"):
            return dict(source._asdict())  # e.g. namedtuple
        if hasattr(source, "__dict__"):
            return {k: v for k, v in vars(source).items() if not k.startswith("_")}
        raise TypeError(f"Unsupported source type for SiteConfig: {type(source)!r}")

    @property
    def start_url(self) -> str:
        return self.url or (f"https://{self.domain}" if self.domain else "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "name": self.name,
            "domain": self.domain,
            "url": self.url,
            "metadata": dict(self.metadata),
            "crawling_strategy": self.crawling_strategy,
        }


class GenericSiteCrawler:
    """Basic crawler that fetches the landing page for a site.

    The implementation intentionally keeps network access optional so the agent
    can operate in restricted environments.  Set
    ``UNIFIED_CRAWLER_ENABLE_HTTP_FETCH=true`` to allow HTTP requests.
    """

    def __init__(
        self,
        site_config: SiteConfig,
        concurrent_browsers: int = 2,
        batch_size: int = 8,
        *,
        enable_http_fetch: bool | None = None,
        session: requests.Session | None = None,
        user_agent_provider: UserAgentProvider | None = None,
        proxy_manager: ProxyManager | None = None,
        stealth_factory: StealthBrowserFactory | None = None,
        modal_handler: ModalHandler | None = None,
        paywall_detector: PaywallDetector | None = None,
        enable_stealth_headers: bool | None = None,
    ):
        self.site_config = site_config
        self.concurrent_browsers = concurrent_browsers
        self.batch_size = batch_size
        resolved = (
            enable_http_fetch
            if enable_http_fetch is not None
            else _bool_from_env(
                os.environ.get("UNIFIED_CRAWLER_ENABLE_HTTP_FETCH"),
                default=True,
            )
        )
        self.enable_http_fetch = resolved
        self.session = session or requests.Session()
        self.user_agent_provider = user_agent_provider
        self.proxy_manager = proxy_manager
        self.stealth_factory = stealth_factory
        self.modal_handler = modal_handler
        self.paywall_detector = paywall_detector
        self.enable_stealth_headers = (
            enable_stealth_headers
            if enable_stealth_headers is not None
            else bool(stealth_factory)
        )
        self._modal_dismissals = 0
        self._cookie_consents = 0

    async def crawl_site(self, max_articles: int = 25) -> list[dict[str, Any]]:
        if not self.enable_http_fetch:
            logger.debug(
                "HTTP fetching disabled via UNIFIED_CRAWLER_ENABLE_HTTP_FETCH; skipping %s",
                self.site_config.domain or self.site_config.name,
            )
            return []

        target_url = self._normalise_target_url(self.site_config.start_url)
        if not target_url:
            # Attempt to unwrap simple list-like values passed through JSON args
            if isinstance(self.site_config.name, list) and self.site_config.name:
                target_url = self._normalise_target_url(self.site_config.name[0])
            elif isinstance(self.site_config.domain, list) and self.site_config.domain:
                target_url = self._normalise_target_url(self.site_config.domain[0])
            elif isinstance(self.site_config.metadata.get("start_url"), list):
                candidate = self.site_config.metadata["start_url"]
                if candidate:
                    target_url = self._normalise_target_url(candidate[0])
            elif isinstance(self.site_config.metadata.get("start_url"), str):
                target_url = self._normalise_target_url(
                    self.site_config.metadata["start_url"]
                )
        if not target_url:
            logger.warning(
                "No URL configured for site %s; skipping", self.site_config.name
            )
            return []

        logger.info("Generic crawler fetching homepage: %s", target_url)

        try:
            html = await asyncio.to_thread(self._fetch_url, target_url)
        except Exception as exc:  # noqa: BLE001 - we keep the crawler resilient
            logger.warning("Failed to fetch homepage %s: %s", target_url, exc)
            return []

        if not html:
            return []

        html, _ = self._apply_modal_handler(html, context="homepage")

        # Extract article links from homepage
        article_urls = self._extract_article_links(html, target_url)
        if not article_urls:
            logger.warning("No article links found on homepage %s", target_url)
            # Fallback: try to extract from homepage itself as a single article
            article = self._build_article(target_url, html)
            return [article] if article else []

        # Fetch and extract articles from the discovered URLs
        articles = []
        semaphore = asyncio.Semaphore(self.concurrent_browsers)

        async def fetch_article(url: str):
            async with semaphore:
                try:
                    logger.debug("Fetching article: %s", url)
                    article_html = await asyncio.to_thread(self._fetch_url, url)
                    if article_html:
                        article_html, modal_result = self._apply_modal_handler(
                            article_html, context="article"
                        )
                        article = self._build_article(url, article_html)
                        if article and self.paywall_detector:
                            detection = await self.paywall_detector.analyze(
                                url=url,
                                html=article_html,
                                text=article.get("content"),
                            )
                            metadata = article.setdefault("extraction_metadata", {})
                            metadata["paywall_detection"] = {
                                "is_paywall": detection.is_paywall,
                                "confidence": detection.confidence,
                                "reasons": detection.reasons,
                            }
                            article["paywall_flag"] = detection.is_paywall
                            if detection.should_skip:
                                logger.debug("Skipping paywalled article %s", url)
                                return None
                        if article:
                            metadata = article.setdefault("extraction_metadata", {})
                            modal_info = {
                                "modal_detected": bool(modal_result.modals_detected)
                                if modal_result
                                else False,
                                "consent_cookies": len(modal_result.applied_cookies)
                                if modal_result
                                else 0,
                            }
                            metadata["modal_handler"] = modal_info
                        return article
                except Exception as exc:
                    logger.debug("Failed to fetch article %s: %s", url, exc)
                return None

        # Create tasks for fetching articles
        tasks = [fetch_article(url) for url in article_urls[:max_articles]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful articles
        for result in results:
            if isinstance(result, Exception):
                logger.debug("Article fetch failed with exception: %s", result)
                continue
            if result:
                articles.append(result)

        logger.info(
            "Successfully extracted %d articles from %s",
            len(articles),
            self.site_config.domain,
        )
        return articles

    def _notify_proxy_failure(self, error: Exception) -> None:
        handler = (
            getattr(self.proxy_manager, "report_failure", None)
            if self.proxy_manager
            else None
        )
        if not callable(handler):
            return
        try:
            handler(error)
        except Exception as exc:  # noqa: BLE001 - keep crawler resilient
            logger.debug("Proxy failure callback raised: %s", exc)

    def _normalise_target_url(self, candidate: Any) -> str:
        """Best-effort URL normaliser that strips duplicate schemes and fills defaults."""
        if candidate is None:
            return ""
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes)):
            candidate = next((item for item in candidate if item), "")
        candidate = str(candidate).strip()
        if not candidate:
            return ""

        # Avoid common double scheme artefacts such as https://https://example.com
        parsed = urlparse(candidate)
        if parsed.scheme and not parsed.netloc and "://" in parsed.path:
            parsed = urlparse(parsed.path)

        scheme = parsed.scheme or "https"
        netloc = parsed.netloc
        path = parsed.path
        params = parsed.params
        query = parsed.query
        fragment = parsed.fragment

        if not netloc:
            fallback = (self.site_config.domain or "").strip()
            if fallback and "://" in fallback:
                fallback = urlparse(fallback).netloc or fallback
            if fallback:
                netloc = fallback
            else:
                # Treat bare domains or paths as implicit netloc values
                if path and not path.startswith("/"):
                    derived = urlparse(f"https://{path}")
                    netloc = derived.netloc or netloc
                    # Preserve sub-path when present after the hostname
                    if derived.path and derived.netloc:
                        path = derived.path

        netloc = netloc.lstrip("/")
        if not netloc:
            return ""

        normalised = urlunparse((scheme, netloc, path, params, query, fragment))
        return normalised.rstrip("/") or normalised

    def _fetch_url(self, url: str) -> str:
        headers: dict[str, str] = {}
        domain = self.site_config.domain or ""
        if not domain:
            parsed = urlparse(url)
            domain = parsed.netloc

        user_agent = None
        if self.user_agent_provider:
            try:
                user_agent = self.user_agent_provider.choose(domain=domain)
            except Exception as exc:  # noqa: BLE001 - rotation is optional
                logger.debug("UserAgentProvider failure for %s: %s", domain, exc)

        profile = None
        if self.stealth_factory and self.enable_stealth_headers:
            if user_agent:
                profile = self.stealth_factory.profile_for_user_agent(user_agent)
            if profile is None:
                profile = self.stealth_factory.random_profile()
            headers.setdefault("Accept-Language", profile.accept_language)
            headers.setdefault("Accept-Encoding", profile.accept_encoding)
            for key, value in profile.headers.items():
                headers.setdefault(key, value)
            user_agent = user_agent or profile.user_agent

        headers.setdefault("User-Agent", user_agent or "JustNewsCrawler/1.0")

        proxies = None
        proxy_in_use = False
        if self.proxy_manager:
            proxy = self.proxy_manager.next_proxy()
            if proxy:
                proxies = {"http": proxy.url, "https": proxy.url}
                proxy_in_use = True

        try:
            response = self.session.get(
                url, timeout=10, headers=headers, proxies=proxies
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as exc:
            if proxy_in_use:
                self._notify_proxy_failure(exc)
            raise

    def _build_article(self, url: str, html: str) -> dict[str, Any] | None:
        extraction: ExtractionOutcome = extract_article_content(html, url)
        if not extraction.text:
            logger.debug("Extraction pipeline returned no content for %s", url)
            return None

        canonical_url = extraction.canonical_url or url
        normalized_url = normalize_article_url(url, canonical_url)
        hash_algorithm = os.environ.get("ARTICLE_URL_HASH_ALGO", "sha256")
        hash_candidate = normalized_url or canonical_url or url
        url_hash = hash_article_url(hash_candidate, algorithm=hash_algorithm)
        timestamp = datetime.now(UTC).isoformat()

        extraction_metadata: dict[str, Any] = {
            "strategy": self.site_config.crawling_strategy,
            "extractor": extraction.extractor_used,
            "fallbacks_attempted": extraction.fallbacks_attempted,
            "word_count": extraction.word_count,
            "boilerplate_ratio": extraction.boilerplate_ratio,
            "needs_review": extraction.needs_review,
            "review_reasons": extraction.review_reasons,
            "raw_html_path": extraction.raw_html_path,
        }
        if extraction.metadata:
            extraction_metadata["extracted_primary"] = extraction.metadata

        article = {
            "url": url,
            "canonical": canonical_url,
            "normalized_url": normalized_url,
            "title": extraction.title or self.site_config.name,
            "content": extraction.text[:10_000],
            "domain": self.site_config.domain,
            "source_name": self.site_config.name,
            "publisher_meta": self.site_config.metadata,
            "extracted_metadata": extraction.metadata,
            "structured_metadata": extraction.structured_metadata,
            "language": extraction.language,
            "authors": extraction.authors,
            "section": extraction.section,
            "tags": extraction.tags,
            "publication_date": extraction.publication_date,
            "confidence": 0.75 if not extraction.needs_review else 0.35,
            "paywall_flag": False,
            "needs_review": extraction.needs_review,
            "extraction_metadata": extraction_metadata,
            "raw_html_ref": extraction.raw_html_path,
            "timestamp": timestamp,
            "url_hash": url_hash,
            "url_hash_algorithm": hash_algorithm,
        }

        return article

    def _apply_modal_handler(
        self, html: str, *, context: str
    ) -> tuple[str, ModalHandlingResult | None]:
        """Run the modal handler while tracking dismissals and consent cookies."""
        if not self.modal_handler:
            return html, None

        modal_result = self.modal_handler.process(html)
        if modal_result.applied_cookies:
            self.session.cookies.update(modal_result.applied_cookies)
            self._cookie_consents += len(modal_result.applied_cookies)
        if modal_result.modals_detected:
            self._modal_dismissals += 1
            notes = "; ".join(modal_result.notes) if modal_result.notes else context
            logger.debug(
                "Consent modal detected for %s (%s)", self.site_config.domain, notes
            )
        return modal_result.cleaned_html, modal_result

    def _extract_article_links(self, html: str, base_url: str) -> list[str]:
        """Extract article links from homepage HTML."""
        if lxml_html is None:
            logger.warning("lxml not available for link extraction")
            return []

        try:
            tree = lxml_html.fromstring(html)
        except Exception as exc:
            logger.warning("Failed to parse HTML for link extraction: %s", exc)
            return []

        # Extract all links
        links = tree.xpath("//a/@href")
        article_urls = []

        for link in links:
            if not link or not isinstance(link, str):
                continue

            # Convert relative URLs to absolute
            if link.startswith("/"):
                # Use the base URL's scheme and netloc
                from urllib.parse import urljoin

                link = urljoin(base_url, link)
            elif not link.startswith("http"):
                continue  # Skip non-HTTP links

            # Filter for article-like URLs
            if self._is_article_url(link):
                article_urls.append(link)

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in article_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        logger.debug(
            f"Extracted {len(unique_urls)} potential article URLs from {self.site_config.domain}"
        )
        return unique_urls[:50]  # Limit to prevent excessive crawling

    def _is_article_url(self, url: str) -> bool:
        """Determine if a URL likely points to an article."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)

            # Must be on the same domain (allow www. prefix)
            base_domain = self.site_config.domain.replace("www.", "")
            url_domain = parsed.netloc.replace("www.", "")
            if base_domain not in url_domain:
                return False

            path = parsed.path.lower()

            # BBC-specific patterns
            if "bbc" in self.site_config.domain.lower():
                # Article patterns for BBC
                if any(
                    pattern in path
                    for pattern in [
                        "/news/",
                        "/sport/",
                        "/business/",
                        "/world/",
                        "/politics/",
                        "/technology/",
                        "/science/",
                        "/health/",
                        "/entertainment/",
                        "/arts/",
                    ]
                ):
                    # Exclude non-article paths
                    if any(
                        exclude in path
                        for exclude in [
                            "/weather/",
                            "/iplayer/",
                            "/sounds/",
                            "/programmes/",
                            "/video/",
                            "/audio/",
                            "/photos/",
                            "/gallery/",
                        ]
                    ):
                        return False
                    # Must have article ID pattern (alphanumeric string at end)
                    last_segment = path.split("/")[-1]
                    if (
                        last_segment and len(last_segment) > 5
                    ):  # Article IDs are typically long alphanumeric strings
                        return True

            # CNN patterns
            elif "cnn" in self.site_config.domain.lower():
                if "/202" in path or "/index.html" in path:  # Recent articles
                    return True

            # Reuters patterns
            elif "reuters" in self.site_config.domain.lower():
                if "/article/" in path or "/world/" in path or "/business/" in path:
                    return True

            # Generic patterns for other news sites
            else:
                # Look for year patterns in URL (common in news sites)
                if "/202" in path or "/201" in path:
                    return True
                # Look for article-like paths
                if any(
                    pattern in path for pattern in ["/article/", "/story/", "/news/"]
                ):
                    return True

            return False

        except Exception:
            return False


class MultiSiteCrawler:
    """Coordinator that uses the generic crawler for multiple sites."""

    def __init__(
        self,
        *,
        enable_http_fetch: bool | None = None,
        user_agent_provider: UserAgentProvider | None = None,
        proxy_manager: ProxyManager | None = None,
        stealth_factory: StealthBrowserFactory | None = None,
        modal_handler: ModalHandler | None = None,
        paywall_detector: PaywallDetector | None = None,
        enable_stealth_headers: bool | None = None,
    ):
        self.enable_http_fetch = enable_http_fetch
        self.user_agent_provider = user_agent_provider
        self.proxy_manager = proxy_manager
        self.stealth_factory = stealth_factory
        self.modal_handler = modal_handler
        self.paywall_detector = paywall_detector
        self.enable_stealth_headers = enable_stealth_headers

    async def crawl_sites(
        self,
        site_configs: Iterable[SiteConfig],
        *,
        max_articles_per_site: int = 25,
        concurrent_sites: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
        results: dict[str, list[dict[str, Any]]] = {}
        semaphore = asyncio.Semaphore(max(1, concurrent_sites))

        async def _crawl_single(config: SiteConfig) -> None:
            async with semaphore:
                crawler = GenericSiteCrawler(
                    config,
                    enable_http_fetch=self.enable_http_fetch,
                    user_agent_provider=self.user_agent_provider,
                    proxy_manager=self.proxy_manager,
                    stealth_factory=self.stealth_factory,
                    modal_handler=self.modal_handler,
                    paywall_detector=self.paywall_detector,
                    enable_stealth_headers=self.enable_stealth_headers,
                )
                articles = await crawler.crawl_site(max_articles=max_articles_per_site)
                results[config.domain or config.name] = articles

        tasks = [asyncio.create_task(_crawl_single(config)) for config in site_configs]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return results
