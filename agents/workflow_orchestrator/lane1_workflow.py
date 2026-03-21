"""Lane 1 orchestration for BBC seed crawl and DDG comparative expansion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from common.ddg_search_service import DdgSearchService
from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class Lane1Config:
    seed_count: int = 10
    max_related_per_seed: int = 5
    ddg_max_queries_per_seed: int = 3
    require_bbc_first: bool = True


class DdgSeedSearchProvider(Protocol):
    def search_related_articles_for_seed(
        self,
        seed_article: dict[str, Any],
        *,
        max_results: int,
        max_queries_per_seed: int,
        excluded_domains: set[str] | None = None,
    ) -> dict[str, Any]: ...


class Lane1Workflow:
    """Build comparative retrieval plan from BBC seed articles."""

    def __init__(
        self,
        ddg_service: DdgSeedSearchProvider | None = None,
        config: Lane1Config | None = None,
    ):
        self.ddg_service = ddg_service or DdgSearchService()
        self.config = config or Lane1Config()

    def _article_source_url(self, article: dict[str, Any]) -> str:
        return str(article.get("source_url") or article.get("url") or "")

    def _article_source_domain(self, article: dict[str, Any]) -> str:
        return str(article.get("source_domain") or article.get("domain") or "")

    def _article_id(self, article: dict[str, Any]) -> Any:
        return article.get("article_id") or article.get("id")

    def _is_bbc_seed(self, article: dict[str, Any]) -> bool:
        domain = self._article_source_domain(article).lower()
        url = self._article_source_url(article).lower()
        return "bbc." in domain or "bbc." in url

    def select_seed_articles(self, articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Select the first N eligible seed articles, preferring BBC when required."""
        if not articles:
            return []

        ordered = list(articles)
        if self.config.require_bbc_first:
            bbc = [article for article in ordered if self._is_bbc_seed(article)]
            if bbc:
                ordered = bbc

        return ordered[: max(1, int(self.config.seed_count))]

    def build_seed_expansion_plan(
        self,
        articles: list[dict[str, Any]],
        *,
        excluded_domains: set[str] | None = None,
    ) -> dict[str, Any]:
        """Build an actionable Lane 1 comparative retrieval plan."""
        seeds = self.select_seed_articles(articles)
        seed_runs: list[dict[str, Any]] = []

        for seed in seeds:
            expanded = self.ddg_service.search_related_articles_for_seed(
                seed,
                max_results=self.config.max_related_per_seed,
                max_queries_per_seed=self.config.ddg_max_queries_per_seed,
                excluded_domains=excluded_domains,
            )
            expanded["seed_source"] = {
                "article_id": self._article_id(seed),
                "source_url": self._article_source_url(seed) or None,
                "source_domain": self._article_source_domain(seed) or None,
            }
            seed_runs.append(expanded)

        total_related = sum(len(run.get("results", [])) for run in seed_runs)
        plan = {
            "lane": "lane1",
            "seed_count": len(seeds),
            "max_related_per_seed": self.config.max_related_per_seed,
            "ddg_max_queries_per_seed": self.config.ddg_max_queries_per_seed,
            "require_bbc_first": self.config.require_bbc_first,
            "seed_runs": seed_runs,
            "total_related_candidates": total_related,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "Lane1 plan generated with %s seeds and %s related candidates",
            len(seeds),
            total_related,
        )
        return plan
