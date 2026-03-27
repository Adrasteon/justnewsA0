"""Utilities for ensuring raw HTML artefacts land in the canonical archive."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from agents.archive.metrics_registry import metrics as archive_metrics
from common.observability import get_logger

logger = get_logger(__name__)


def _default_service_dir() -> Path:
    return Path(
        os.environ.get("SERVICE_DIR", Path(__file__).resolve().parents[2])
    ).resolve()


def _default_raw_dir(service_dir: Path) -> Path:
    candidate = os.environ.get("JUSTNEWS_RAW_HTML_DIR")
    return (
        Path(candidate) if candidate else service_dir / "archive_storage" / "raw_html"
    ).resolve()


def _ensure_relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def ensure_raw_html_artifact(
    raw_html_ref: str | None,
    *,
    service_dir: Path | None = None,
    canonical_root: Path | None = None,
) -> dict[str, Any]:
    """Validate and, if needed, copy the raw HTML artefact into the canonical archive.

    Returns a payload containing the updated reference path alongside bookkeeping
    metadata that callers can log or attach to responses.
    """

    start = perf_counter()
    service_dir = (service_dir or _default_service_dir()).resolve()
    canonical_root = (canonical_root or _default_raw_dir(service_dir)).resolve()

    canonical_root.mkdir(parents=True, exist_ok=True)

    if not raw_html_ref:
        archive_metrics.increment("raw_html_missing_total")
        archive_metrics.timing("raw_html_check_latency_seconds", perf_counter() - start)
        return {
            "status": "missing_ref",
            "raw_html_ref": None,
            "source_path": None,
            "destination_path": None,
        }

    candidate = Path(raw_html_ref)
    if not candidate.is_absolute():
        candidate = (service_dir / candidate).resolve(strict=False)
    else:
        candidate = candidate.resolve(strict=False)

    response: dict[str, Any] = {
        "source_path": str(candidate),
        "destination_path": None,
        "raw_html_ref": raw_html_ref,
        "status": "unprocessed",
    }

    if not candidate.exists():
        archive_metrics.increment("raw_html_missing_total")
        archive_metrics.timing("raw_html_check_latency_seconds", perf_counter() - start)
        response.update({"status": "missing_source", "raw_html_ref": None})
        logger.warning("Raw HTML reference missing on disk: %s", candidate)
        return response

    if candidate.is_relative_to(canonical_root):
        archive_metrics.increment("raw_html_verified_total")
        archive_metrics.timing("raw_html_check_latency_seconds", perf_counter() - start)
        response.update(
            {
                "status": "verified",
                "raw_html_ref": _ensure_relative(candidate, service_dir),
                "destination_path": str(candidate),
            }
        )
        return response

    dest_dir = canonical_root / datetime.now(UTC).strftime("%Y/%m/%d")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / candidate.name
    counter = 1
    while dest_path.exists():
        suffix = candidate.suffix or ".html"
        dest_path = dest_dir / f"{candidate.stem}_{counter}{suffix}"
        counter += 1

    try:
        shutil.copy2(candidate, dest_path)
        archive_metrics.increment("raw_html_copied_total")
        archive_metrics.timing("raw_html_check_latency_seconds", perf_counter() - start)
        response.update(
            {
                "status": "copied",
                "destination_path": str(dest_path),
                "raw_html_ref": _ensure_relative(dest_path, service_dir),
            }
        )
        logger.debug("Copied raw HTML artefact %s -> %s", candidate, dest_path)
        return response
    except Exception as exc:  # noqa: BLE001
        archive_metrics.increment("raw_html_copy_failure_total")
        archive_metrics.timing("raw_html_check_latency_seconds", perf_counter() - start)
        response.update({"status": "copy_failed", "raw_html_ref": None})
        logger.error("Failed to copy raw HTML artefact %s: %s", candidate, exc)
        return response


__all__ = ["ensure_raw_html_artifact"]
