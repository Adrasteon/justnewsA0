"""Ingest adapter helpers for mapping crawler payloads to DB-ready operations.

This module provides small, dependency-free helper functions used by agents to
prepare upsert statements and article_source_map payloads. For Phase 1 these are
stubs designed to be used by unit tests and later wired to the real DB code or
agent-driven transactions via `mcp_bus`.
"""

import json
from typing import Any

# This module intentionally avoids DB driver imports at top-level. For
# production use we route to the migrated MariaDB helper when needed.


def build_source_upsert(payload: dict[str, Any]) -> tuple[str, tuple]:
    """Return a MariaDB-compatible upsert SQL and params for `sources`.

    Uses `INSERT ... ON DUPLICATE KEY UPDATE` and does not rely on RETURNING.
    The caller should obtain the inserted id via cursor.lastrowid when needed.
    """
    sql = (
        "INSERT INTO sources (url, url_hash, domain, canonical, metadata, created_at)"
        " VALUES (%s, %s, %s, %s, %s, NOW())"
        " ON DUPLICATE KEY UPDATE canonical=VALUES(canonical), metadata=VALUES(metadata), updated_at=NOW();"
    )

    params = (
        payload.get("url"),
        payload.get("url_hash"),
        payload.get("domain"),
        payload.get("canonical"),
        json.dumps(payload.get("publisher_meta", {})),
    )

    return sql, params


def build_article_source_map_insert(
    article_id: int, source_payload: dict[str, Any]
) -> tuple[str, tuple]:
    """Build SQL and params for inserting into article_source_map.

    Expects article_id and source_payload with url_hash, confidence, paywall_flag, and extraction_metadata
    """
    sql = (
        "INSERT INTO public.article_source_map (article_id, source_url_hash, confidence, paywall_flag, metadata, created_at)"
        " VALUES (%s, %s, %s, %s, %s, now());"
    )

    params = (
        article_id,
        source_payload.get("url_hash"),
        source_payload.get("confidence", 0.5),
        source_payload.get("paywall_flag", False),
        json.dumps(source_payload.get("extraction_metadata", {})),
    )

    return sql, params


def canonical_selection_rule(candidates: list) -> dict[str, Any]:
    """Simple canonical selection implementation used for testing.

    candidates: list of dicts with keys ['source_id'|'url_hash', 'confidence', 'timestamp', 'matched_by']
    Returns chosen candidate dict.
    """
    if not candidates:
        return {}

    # Sort by confidence desc, timestamp desc, matched_by==ingest preferred
    def score(c):
        conf = float(c.get("confidence", 0.0))
        ts = c.get("timestamp") or ""
        matched = 1 if c.get("matched_by") == "ingest" else 0
        return (conf, ts, matched)

    sorted_candidates = sorted(candidates, key=score, reverse=True)
    return sorted_candidates[0]


def ingest_article(article_payload: dict[str, Any], db_execute) -> dict[str, Any]:
    """High-level ingest helper that performs a transactional upsert of source,
    inserts article_source_map and returns the chosen canonical candidate using
    the simple canonical selection rule.

    db_execute: callable(sql, params) -> returns lastrowid or None. This is
    intentionally abstract to allow using sqlite3 in-memory tests or a real
    DB driver in production.
    """
    # Upsert source
    source_sql, source_params = build_source_upsert(article_payload)
    source_id = db_execute(source_sql, source_params)

    # Simulate obtaining article_id (in a real system articles table would be used)
    article_id = article_payload.get("article_id") or 1

    # Insert article_source_map
    asm_sql, asm_params = build_article_source_map_insert(article_id, article_payload)
    db_execute(asm_sql, asm_params)

    # For canonical selection, fetch candidates (in tests we will pass them)
    # Here, we simulate by returning the single candidate created
    candidate = {
        "source_id": source_id,
        "url_hash": article_payload.get("url_hash"),
        "confidence": article_payload.get("confidence", 0.5),
        "timestamp": article_payload.get("timestamp"),
        "matched_by": article_payload.get("matched_by", "ingest"),
    }

    canonical = canonical_selection_rule([candidate])

    # Do not execute update by default; leave to orchestrator or DB stored proc

    return {"source_id": source_id, "article_id": article_id, "canonical": canonical}


def ingest_article_db(article_payload: dict[str, Any], dsn: str) -> dict[str, Any]:
    """Execute the ingest using the migrated MariaDB-backed service.

    This will perform the source upsert and insert article_source_map inside
    a single transaction and return the chosen canonical candidate.
    """
    # Use the migrated DB service so we don't depend on a specific DB driver
    from database.utils.migrated_database_utils import create_database_service

    service = create_database_service()

    source_sql, source_params = build_source_upsert(article_payload)
    asm_sql, asm_params = build_article_source_map_insert(
        article_payload.get("article_id", 1), article_payload
    )

    try:
        conn = service.get_connection()
        cursor = conn.cursor()
        try:
            # Run source upsert
            cursor.execute(source_sql, source_params)
            # Obtain inserted/updated id: prefer lastrowid, fallback to select
            source_id = cursor.lastrowid if hasattr(cursor, "lastrowid") else None
            if not source_id:
                # Try to lookup by url_hash
                try:
                    # Use a buffered dictionary cursor on the same per-call connection
                    lookup_cur = conn.cursor(dictionary=True, buffered=True)
                    lookup_cur.execute(
                        "SELECT id FROM sources WHERE url_hash = %s",
                        (article_payload.get("url_hash"),),
                    )
                    row = lookup_cur.fetchone()
                    lookup_cur.close()
                    source_id = row.get("id") if row else None
                except Exception:
                    source_id = None

            # Insert article_source_map
            cursor.execute(asm_sql, asm_params)

            # Commit transaction
            conn.commit()

            # Build candidate and canonical rule
            candidate = {
                "source_id": source_id,
                "url_hash": article_payload.get("url_hash"),
                "confidence": article_payload.get("confidence", 0.5),
                "timestamp": article_payload.get("timestamp"),
                "matched_by": article_payload.get("matched_by", "ingest"),
            }

            canonical = canonical_selection_rule([candidate])

            return {
                "source_id": source_id,
                "article_id": article_payload.get("article_id", 1),
                "canonical": canonical,
            }
        finally:
            try:
                cursor.close()
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
