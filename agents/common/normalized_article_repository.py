from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from agents.common.agent_chain_harness import NormalizedArticle
from common.observability import get_logger
from database.models.migrated_models import MigratedDatabaseService
from database.utils.migrated_database_utils import create_database_service

logger = get_logger(__name__)


@dataclass
class ArticleCandidate:
    """Container holding the DB row and the normalized article payload."""

    row: dict
    article: NormalizedArticle


class NormalizedArticleRepository:
    """Retrieve normalized article rows that are ready for the agent chain harness."""

    def __init__(self, db_service: MigratedDatabaseService | None = None) -> None:
        svc = db_service or create_database_service()
        try:
            from database.utils.migrated_database_utils import ensure_service_compat

            svc = ensure_service_compat(svc)
        except Exception:
            pass
        self.db_service = svc

    def fetch_candidates(
        self,
        *,
        limit: int = 5,
        article_ids: Sequence[int | str] | None = None,
        min_chars: int = 400,
    ) -> list[ArticleCandidate]:
        """Return normalized articles with sufficient content that still need editorial runs."""

        if limit <= 0:
            return []

        # Use a per-call buffered dictionary cursor to avoid sharing resultsets
        # across concurrent fetches which can cause 'Unread result found'.
        # We keep ensure_conn for backward compatibility, but prefer per-call connections.
        try:
            self.db_service.ensure_conn()
        except Exception:
            # ensure_conn is best-effort; proceed to per-call connection
            pass
        cursor, conn = self.db_service.get_safe_cursor(
            per_call=True, dictionary=True, buffered=True
        )
        params: list = [min_chars]
        filters: list[str] = [
            "(content IS NOT NULL AND CHAR_LENGTH(content) >= %s)",
            "(is_synthesized = 0 OR is_synthesized IS NULL)",
            "(fact_check_status IS NULL OR fact_check_status IN ('', 'pending', 'needs_followup'))",
        ]

        if article_ids:
            placeholders = ",".join(["%s"] * len(article_ids))
            filters.append(f"id IN ({placeholders})")
            params.extend(article_ids)

        where_clause = " AND ".join(filters)
        query = f"""
            SELECT
                id,
                url,
                title,
                content,
                summary,
                metadata,
                structured_metadata,
                authors,
                publication_date,
                needs_review,
                fact_check_status,
                is_synthesized
            FROM articles
            WHERE {where_clause}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT %s
        """
        params.append(limit)

        try:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall() or []
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

        candidates: list[ArticleCandidate] = []
        for row in rows:
            text = (row.get("content") or "").strip() or (
                row.get("summary") or ""
            ).strip()
            if not text or len(text) < min_chars:
                logger.debug(
                    "Skipping article %s due to insufficient text", row.get("id")
                )
                continue

            metadata = self._build_metadata(row)
            article = NormalizedArticle(
                article_id=str(row.get("id")),
                url=row.get("url") or metadata.get("canonical_url") or "",
                title=row.get("title")
                or metadata.get("title")
                or metadata.get("headline")
                or "Untitled",
                text=text,
                metadata=metadata,
            )
            candidates.append(ArticleCandidate(row=row, article=article))

        return candidates

    @staticmethod
    def _build_metadata(row: dict) -> dict:
        metadata = _coerce_json(row.get("metadata"))
        structured_meta = _coerce_json(row.get("structured_metadata"))
        authors = _ensure_list(_coerce_json(row.get("authors")))

        enriched = {
            "raw": metadata,
            "structured": structured_meta,
            "authors": authors,
            "publication_date": row.get("publication_date"),
            "needs_review": row.get("needs_review"),
            "fact_check_status": row.get("fact_check_status"),
        }
        # Include useful fallbacks for downstream logging/debugging
        if metadata and metadata.get("url"):
            enriched.setdefault("canonical_url", metadata.get("url"))
        if structured_meta and structured_meta.get("canonical_url"):
            enriched.setdefault("canonical_url", structured_meta.get("canonical_url"))
        if structured_meta and structured_meta.get("title"):
            enriched.setdefault("title", structured_meta.get("title"))
        return enriched


def _coerce_json(value: object) -> dict | list | str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.debug("Failed to decode JSON payload: %s", value[:120])
            return None
    return None


def _ensure_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
