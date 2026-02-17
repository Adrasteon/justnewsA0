import json
from typing import Any

import database.utils.migrated_database_utils as db_utils
from common.observability import get_logger

logger = get_logger(__name__)


def _make_chroma_metadata_safe(metadata: dict[str, Any]) -> dict[str, Any]:
    # Minimal sanitize helper, reuse from other agents if needed
    safe = metadata.copy() if metadata is not None else {}
    # Add a marker for synthesized
    safe.setdefault("is_synthesized", True)
    # Add embedding model metadata for traceability
    import os

    model = (
        os.environ.get("EMBEDDING_MODEL")
        or os.environ.get("SENTENCE_TRANSFORMER_MODEL")
        or "all-MiniLM-L6-v2"
    )
    dims = os.environ.get("EMBEDDING_DIMENSIONS")
    safe.setdefault("embedding_model", model)
    if dims:
        try:
            safe.setdefault("embedding_dimensions", int(dims))
        except Exception:
            pass
    return safe


def save_synthesized_draft(
    story_id: str,
    title: str,
    body: str,
    summary: str | None = None,
    analysis_summary: dict[str, Any] | None = None,
    synth_metadata: dict[str, Any] | None = None,
    persistence_mode: str = "extend",
    embedding: list[float] | None = None,
) -> dict[str, Any]:
    """Persist synthesized draft either by extending articles (Option A) or as a SynthesizedArticle (Option B).

    Uses the `create_database_service()` helper to access MariaDB and Chroma.

    Returns a dict with status and database ids.
    """
    db_service = None
    try:
        db_service = db_utils.create_database_service()
        db_service = db_utils.ensure_service_compat(db_service)
        conn = db_service.get_connection()
        cursor = conn.cursor()

        if persistence_mode == "extend":
            # Create a new article row as a synthesized article
            insert_query = (
                "INSERT INTO articles (title, content, summary, is_synthesized, metadata, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, NOW(), NOW())"
            )
            metadata_payload = json.dumps(synth_metadata or {})
            cursor.execute(insert_query, (title, body, summary, True, metadata_payload))
            conn.commit()
            last_id = cursor.lastrowid
            # Add to Chroma if embedding provided
            try:
                if getattr(db_service, "collection", None) and embedding is not None:
                    db_service.collection.add(
                        ids=[str(last_id)],
                        embeddings=[list(map(float, embedding))],
                        metadatas=[
                            _make_chroma_metadata_safe(
                                {"story_id": story_id, "title": title}
                            )
                        ],
                        documents=[body],
                    )
            except Exception:
                logger.exception("Chroma add failed for synthesized article")

            return {"status": "success", "id": last_id, "mode": "extend"}

        else:
            # Option B: insert into synthesized_articles table
            insert_query = (
                "INSERT INTO synthesized_articles (story_id, cluster_id, input_articles, title, body, summary, reasoning_plan, analysis_summary, synth_metadata, created_at, updated_at, is_published)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)"
            )
            # For now, cluster_id and input_articles left None/empty
            cursor.execute(
                insert_query,
                (
                    story_id,
                    None,
                    None,
                    title,
                    body,
                    summary,
                    json.dumps(None),
                    json.dumps(analysis_summary or {}),
                    json.dumps(synth_metadata or {}),
                    False,
                ),
            )
            conn.commit()
            last_id = cursor.lastrowid

            try:
                if getattr(db_service, "collection", None) and embedding is not None:
                    db_service.collection.add(
                        ids=[str(last_id)],
                        embeddings=[list(map(float, embedding))],
                        metadatas=[
                            _make_chroma_metadata_safe(
                                {"story_id": story_id, "title": title}
                            )
                        ],
                        documents=[body],
                    )
            except Exception:
                logger.exception("Chroma add failed for synthesized article (option B)")

            return {"status": "success", "id": last_id, "mode": "synthesized_articles"}

    except Exception as e:
        logger.exception("Failed to save synthesized draft: %s", e)
        return {"status": "error", "error": str(e)}
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass
        try:
            if db_service:
                db_service.close()
        except Exception:
            pass
