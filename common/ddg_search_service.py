"""Reusable DuckDuckGo search service for comparative article retrieval."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from common.observability import get_logger

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover
    DDGS = None

logger = get_logger(__name__)


@dataclass
class DdgSearchResult:
    title: str
    url: str
    snippet: str | None = None
    source_domain: str | None = None
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_domain": self.source_domain,
            "rank": self.rank,
        }


class DdgSearchService:
    """Wrapper around DuckDuckGo search with filtering and provenance support."""

    def __init__(
        self,
        *,
        max_results_default: int = 10,
        timeout_seconds: float = 10.0,
    ):
        self.max_results_default = max(1, int(max_results_default))
        self.timeout_seconds = max(1.0, float(timeout_seconds))

        # Default-on strict filtering to avoid low-quality comparative sources.
        self.strict_domain_filter = (
            str(os.environ.get("DDG_STRICT_DOMAIN_FILTER", "true")).strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.require_news_domain = (
            str(os.environ.get("DDG_REQUIRE_NEWS_DOMAIN", "true")).strip().lower()
            in {"1", "true", "yes", "on"}
        )

    def _is_low_quality_domain(self, domain: str | None) -> bool:
        if not domain:
            return True

        d = domain.lower().strip()
        if not d:
            return True

        blocked_exact = {
            "twitter.com",
            "x.com",
            "facebook.com",
            "instagram.com",
            "linkedin.com",
            "youtube.com",
            "tiktok.com",
            "reddit.com",
            "quora.com",
            "pinterest.com",
            "tumblr.com",
            "forumgratuit.org",
            "forums.blizzard.com",
            "apps.apple.com",
            "zhidao.baidu.com",
            "www.britannica.com",
            "en.wiktionary.org",
        }
        blocked_contains = (
            "forum",
            "discuss",
            "community",
            "wiki",
            "wiktionary",
            "dictionary",
            "encyclopedia",
            "blogspot",
            "fandom",
            "stackexchange",
            "wikia",
            "baidu",
        )

        if d in blocked_exact:
            return True
        if any(token in d for token in blocked_contains):
            return True
        return False

    def _looks_like_news_domain(self, domain: str | None) -> bool:
        if not domain:
            return False

        d = domain.lower().strip()
        if not d:
            return False

        trusted_exact = {
            "apnews.com",
            "www.apnews.com",
            "reuters.com",
            "www.reuters.com",
            "bbc.com",
            "www.bbc.com",
            "bbc.co.uk",
            "www.bbc.co.uk",
            "cnn.com",
            "www.cnn.com",
            "nytimes.com",
            "www.nytimes.com",
            "wsj.com",
            "www.wsj.com",
            "ft.com",
            "www.ft.com",
            "theguardian.com",
            "www.theguardian.com",
            "bloomberg.com",
            "www.bloomberg.com",
        }
        news_tokens = (
            "news",
            "times",
            "post",
            "herald",
            "tribune",
            "chronicle",
            "journal",
            "gazette",
            "observer",
            "dispatch",
            "telegraph",
            "press",
            "standard",
            "economist",
            "independent",
            "media",
        )

        if d in trusted_exact:
            return True
        if any(token in d for token in news_tokens):
            return True
        return False

    def _extract_domain(self, url: str | None) -> str | None:
        if not url:
            return None
        try:
            return (urlparse(url).netloc or "").lower() or None
        except Exception:
            return None

    def _run_ddg_text(self, query: str, max_results: int) -> list[dict[str, Any]]:
        if DDGS is None:
            raise RuntimeError("ddgs is unavailable")
        with DDGS(timeout=int(self.timeout_seconds)) as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    def search_web(
        self,
        query: str,
        *,
        max_results: int | None = None,
        excluded_domains: set[str] | None = None,
        required_distinct_domains: int | None = None,
    ) -> list[DdgSearchResult]:
        """Run a web search and return deduplicated, filtered article candidates."""
        if not query or not query.strip():
            return []

        limit = max(1, int(max_results or self.max_results_default))
        blocked = {d.lower() for d in (excluded_domains or set()) if d}

        try:
            raw_results = self._run_ddg_text(query.strip(), max_results=limit * 3)
        except Exception as exc:
            logger.warning("DuckDuckGo search failed for query '%s': %s", query, exc)
            return []

        seen_urls: set[str] = set()
        seen_domains: set[str] = set()
        out: list[DdgSearchResult] = []

        for raw in raw_results:
            url = str(raw.get("href") or raw.get("url") or "").strip()
            if not url or url in seen_urls:
                continue

            domain = self._extract_domain(url)
            if domain and domain in blocked:
                continue
            if self.strict_domain_filter and self._is_low_quality_domain(domain):
                continue
            if self.require_news_domain and not self._looks_like_news_domain(domain):
                continue

            title = str(raw.get("title") or "").strip() or url
            snippet = str(raw.get("body") or raw.get("snippet") or "").strip() or None

            seen_urls.add(url)
            if domain:
                seen_domains.add(domain)

            out.append(
                DdgSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    source_domain=domain,
                    rank=len(out) + 1,
                )
            )

            if len(out) >= limit:
                break

        if required_distinct_domains and len(seen_domains) < required_distinct_domains:
            logger.info(
                "DDG query '%s' returned %s distinct domains; requested at least %s",
                query,
                len(seen_domains),
                required_distinct_domains,
            )

        return out

    def build_seed_queries(
        self,
        *,
        seed_title: str,
        entities: list[str] | None = None,
        claims: list[str] | None = None,
        max_queries: int = 3,
    ) -> list[str]:
        """Derive practical search queries from title plus extracted entities and claims."""
        queries: list[str] = []
        title = (seed_title or "").strip()
        if title:
            queries.append(title)

        for entity in entities or []:
            entity_text = str(entity or "").strip()
            if entity_text and title:
                queries.append(f"{title} {entity_text}")

        for claim in claims or []:
            claim_text = str(claim or "").strip()
            if claim_text:
                queries.append(claim_text)

        deduped: list[str] = []
        seen: set[str] = set()
        for query in queries:
            key = query.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(query)
            if len(deduped) >= max(1, int(max_queries)):
                break

        return deduped

    def search_related_articles_for_seed(
        self,
        seed_article: dict[str, Any],
        *,
        max_results: int = 5,
        max_queries_per_seed: int = 3,
        excluded_domains: set[str] | None = None,
    ) -> dict[str, Any]:
        """Search corroborating or contrasting coverage for one seed article."""
        seed_title = str(seed_article.get("title") or "").strip()
        entity_names = [
            str(item.get("name") or "").strip()
            for item in (seed_article.get("entities") or [])
            if isinstance(item, dict)
        ]
        claim_texts = [
            str(item.get("claim_text") or "").strip()
            for item in (seed_article.get("claims") or [])
            if isinstance(item, dict)
        ]

        queries = self.build_seed_queries(
            seed_title=seed_title,
            entities=[name for name in entity_names if name],
            claims=[claim for claim in claim_texts if claim],
            max_queries=max_queries_per_seed,
        )

        candidates: list[DdgSearchResult] = []
        seen_urls: set[str] = set()
        for query in queries:
            for result in self.search_web(
                query,
                max_results=max_results,
                excluded_domains=excluded_domains,
            ):
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                candidates.append(result)
                if len(candidates) >= max_results:
                    break
            if len(candidates) >= max_results:
                break

        return {
            "seed_article_id": seed_article.get("article_id"),
            "seed_title": seed_title,
            "queries": queries,
            "results": [result.to_dict() for result in candidates],
            "expanded_at": datetime.now(UTC).isoformat(),
        }
