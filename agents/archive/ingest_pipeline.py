"""Stage 2 ingest plumbing for the archive agent.

This module receives HITL ingest payloads, normalizes them, and forwards the
content into the Stage B storage pipeline (MariaDB + Chroma) by reusing the
memory agent's `save_article` helper. The goal is to make HITL labels
immediately persistable via the archive agent's MCP tool surface.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from agents.archive.metrics_registry import metrics as archive_metrics
from agents.archive.raw_html_snapshot import ensure_raw_html_artifact
from agents.memory.tools import save_article
from common.observability import get_logger
from common.url_normalization import hash_article_url, normalize_article_url

logger = get_logger(__name__)


def _iso_timestamp(value: str | None, *, default_now: bool = True) -> str | None:
    if not value:
        return datetime.now(UTC).isoformat() if default_now else None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).isoformat()
    except Exception:
        return value


def _ensure_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(entry).strip() for entry in value if str(entry).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return []


def _coerce_source_id(site_id: Any) -> int | None:
    if site_id is None:
        return None
    if isinstance(site_id, int):
        return site_id
    if isinstance(site_id, str):
        cleaned = site_id.strip()
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _build_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = payload["candidate"]
    features = candidate.get("features") or {}

    url = candidate.get("url") or ""
    canonical = candidate.get("canonical") or features.get("canonical_url") or url
    normalized_url = normalize_article_url(url, canonical)

    hash_algorithm = (
        payload.get("hash_algorithm")
        or os.environ.get("ARTICLE_URL_HASH_ALGO", "sha256")
    ).lower()
    hash_input = normalized_url or canonical or url
    url_hash = hash_article_url(hash_input, algorithm=hash_algorithm)

    content_summary = (
        payload.get("cleaned_text") or candidate.get("extracted_text") or ""
    ).strip()
    summary = content_summary[:500]

    publisher_meta = {
        "site_id": candidate.get("site_id"),
        "crawler_job_id": candidate.get("crawler_job_id"),
        "ingest_job_id": payload.get("job_id"),
        "candidate_id": payload.get("candidate_id"),
        "label_id": payload.get("label_id"),
        "annotator_id": payload.get("annotator_id"),
    }

    extraction_metadata = {
        "hitl": {
            "label": payload.get("label"),
            "needs_cleanup": payload.get("needs_cleanup"),
            "annotator_id": payload.get("annotator_id"),
            "created_at": payload.get("created_at"),
        },
        "features": features,
    }

    confidence_value = features.get("confidence")
    try:
        confidence = float(confidence_value)
    except (TypeError, ValueError):
        confidence = 0.6

    metadata = {
        "url": url,
        "canonical": canonical or url,
        "normalized_url": normalized_url,
        "title": candidate.get("extracted_title") or features.get("title") or url,
        "summary": summary,
        "domain": _extract_domain(url),
        "publisher_meta": publisher_meta,
        "confidence": confidence,
        "paywall_flag": bool(features.get("paywall_flag")),
        "extraction_metadata": extraction_metadata,
        "structured_metadata": features.get("structured_metadata") or {},
        "timestamp": _iso_timestamp(payload.get("created_at")),
        "collection_timestamp": _iso_timestamp(
            candidate.get("candidate_ts") or payload.get("created_at")
        ),
        "language": features.get("language"),
        "authors": _ensure_list(features.get("authors")),
        "section": features.get("section"),
        "tags": _ensure_list(features.get("tags")),
        "publication_date": features.get("publication_date"),
        "raw_html_ref": candidate.get("raw_html_ref"),
        "needs_review": bool(
            payload.get("needs_cleanup") or features.get("needs_review")
        ),
        "review_reasons": _ensure_list(features.get("review_reasons")),
        "source_id": _coerce_source_id(candidate.get("site_id")),
        "url_hash": url_hash or None,
        "url_hash_algorithm": hash_algorithm,
    }

    return metadata


def queue_article(job_payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a HITL ingest payload via the Stage B storage helper."""

    start_time = perf_counter()
    if not isinstance(job_payload, dict):
        archive_metrics.increment("ingest_failure_total")
        archive_metrics.timing("ingest_latency_seconds", perf_counter() - start_time)
        raise ValueError("ingest payload must be a JSON object")

    candidate = job_payload.get("candidate")
    if not isinstance(candidate, dict):
        archive_metrics.increment("ingest_failure_total")
        archive_metrics.timing("ingest_latency_seconds", perf_counter() - start_time)
        raise ValueError("ingest payload missing candidate data")

    content = (
        job_payload.get("cleaned_text") or candidate.get("extracted_text") or ""
    ).strip()
    if not content:
        archive_metrics.increment("ingest_failure_total")
        archive_metrics.timing("ingest_latency_seconds", perf_counter() - start_time)
        raise ValueError("ingest payload requires cleaned_text or extracted_text")

    metadata = _build_metadata(job_payload)
    snapshot = ensure_raw_html_artifact(metadata.get("raw_html_ref"))
    if snapshot.get("raw_html_ref"):
        metadata["raw_html_ref"] = snapshot["raw_html_ref"]
    elif snapshot.get("status") in {"missing_source", "copy_failed"}:
        logger.warning(
            "Raw HTML artifact missing for candidate %s (status=%s, source=%s)",
            job_payload.get("candidate_id"),
            snapshot.get("status"),
            snapshot.get("source_path"),
        )

    logger.info(
        "Queueing article from candidate %s (job=%s, url=%s)",
        job_payload.get("candidate_id"),
        job_payload.get("job_id"),
        metadata.get("url"),
    )

    try:
        result = save_article(content, metadata)
    except Exception:
        archive_metrics.increment("ingest_failure_total")
        archive_metrics.timing("ingest_latency_seconds", perf_counter() - start_time)
        raise

    if result.get("error"):
        archive_metrics.increment("ingest_failure_total")
        archive_metrics.timing("ingest_latency_seconds", perf_counter() - start_time)
        raise RuntimeError(f"save_article failed: {result['error']}")

    status = result.get("status") or "success"
    elapsed = perf_counter() - start_time
    if status == "success":
        archive_metrics.increment("ingest_success_total")
    elif status == "duplicate":
        archive_metrics.increment("ingest_duplicate_total")
    else:
        archive_metrics.increment("ingest_failure_total")
    archive_metrics.timing("ingest_latency_seconds", elapsed)

    response = {
        "status": status,
        "article_id": result.get("article_id"),
        "duplicate": status == "duplicate",
        "job_id": job_payload.get("job_id"),
        "candidate_id": job_payload.get("candidate_id"),
        "normalized_url": metadata.get("normalized_url"),
        "url_hash": metadata.get("url_hash"),
    }
    return response
