from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.observability import get_logger

try:
    # DB service is heavy to import in test contexts - lazily import when needed
    create_database_service = None
except Exception:
    create_database_service = None
from agents.dashboard.transparency_repository import default_repository

logger = get_logger(__name__)


@dataclass
class ArticleRecord:
    article_id: str
    content: str
    url: str | None = None
    title: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "content": self.content,
            "url": self.url,
            "title": self.title,
            "metadata": self.metadata,
        }


class ClusterFetcher:
    """Fetch article content for a cluster using Chroma, MariaDB, or the Transparency repository.

    This class provides a small set of helpers to fetch and normalize article content for downstream
    agents (Analyst, FactChecker, Reasoning, Synthesizer). The implementation focuses on being
    robust in the face of missing infrastructure by working with available data sources and
    providing sensible defaults.
    """

    def __init__(self, db_service=None):
        if db_service is None:
            from database.utils.migrated_database_utils import (
                create_database_service as _create_db,
            )

            self.db_service = _create_db()
        else:
            self.db_service = db_service

    def fetch_cluster(
        self,
        cluster_id: str | None = None,
        article_ids: list[str] | None = None,
        max_results: int = 50,
        dedupe: bool = True,
    ) -> list[ArticleRecord]:
        """
        Fetch normalized article records for a cluster id or list of article ids.

        Args:
            cluster_id: optional cluster identifier (transparency index based)
            article_ids: optional list of article ids to fetch directly
            max_results: maximum number of results
            dedupe: whether to de-duplicate repeated content

        Returns:
            List of ArticleRecord objects
        """
        articles: list[ArticleRecord] = []

        # First: attempt to read cluster membership from the Transparency repository if a cluster_id is given.
        member_article_ids: list[str] = []
        if cluster_id:
            try:
                repo = default_repository()
                cluster_payload = repo.get_cluster(cluster_id)
                member_articles = cluster_payload.get("cluster", {}).get(
                    "member_articles", []
                )
                member_article_ids = [
                    m.get("article_id") for m in member_articles if m.get("article_id")
                ]
            except Exception:
                logger.debug(
                    "Transparency cluster not found or couldn't be loaded for cluster_id=%s",
                    cluster_id,
                    exc_info=True,
                )

        # If explicit article_ids are provided, they override cluster list
        if article_ids:
            id_list = article_ids
        else:
            id_list = member_article_ids

        # If no ids, return empty list early
        if not id_list:
            logger.info(
                "No article ids provided or discovered for cluster_id=%s", cluster_id
            )
            return []

        # Fetch each article from MariaDB
        try:
            # Use dictionary cursor so rows are easier to work with across tests
            for aid in id_list[:max_results]:
                try:
                    cursor = self.db_service.mb_conn.cursor(dictionary=True)
                    cursor.execute(
                        "SELECT id, url, title, content, metadata FROM articles WHERE id = %s",
                        (aid,),
                    )
                    row = cursor.fetchone()
                    cursor.close()
                except Exception:
                    # Fallback: if a DB error occurs, skip this id but continue
                    logger.warning(
                        "Failed to fetch article %s from DB", aid, exc_info=True
                    )
                    continue

                if not row:
                    logger.warning("Article %s not found in DB; skipping", aid)
                    continue

                # Normalize metadata field if needed
                meta = row.get("metadata")
                if isinstance(meta, str):
                    try:
                        import json

                        meta = json.loads(meta)
                    except Exception:
                        meta = {"raw": meta}

                article = ArticleRecord(
                    article_id=str(row.get("id") or aid),
                    content=row.get("content") or "",
                    url=row.get("url"),
                    title=row.get("title"),
                    metadata=meta,
                )

                articles.append(article)

        except Exception:
            logger.exception("Unexpected error while fetching cluster data")

        # Optional de-duplication: by URL and content
        if dedupe and articles:
            seen_urls = set()
            unique_articles: list[ArticleRecord] = []
            for a in articles:
                url = (a.url or "").strip().lower()
                content_key = (a.content or "").strip()[:512]
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_articles.append(a)
                else:
                    # If URL missing, try content dedupe
                    if not url:
                        # naive content-based dedupe using first N chars
                        if not any(
                            (content_key == (ua.content or "").strip()[:512])
                            for ua in unique_articles
                        ):
                            unique_articles.append(a)
            articles = unique_articles

        return articles


__all__ = ["ClusterFetcher", "ArticleRecord"]
