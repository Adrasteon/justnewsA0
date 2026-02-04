"""Utilities for summarising adaptive crawl metadata.

This module provides helper functions to aggregate per-article adaptive
telemetry emitted by Crawl4AI into concise statistics that can be surfaced in
scheduler metrics and dashboards.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any

Number = float | int


def _coerce_float(value: Any) -> float | None:
    """Attempt to coerce the given value to ``float``; return ``None`` on failure."""

    if isinstance(value, bool):  # bool is subclass of int; treat as invalid here
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _build_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "sum": 0.0}

    total = sum(values)
    stats: dict[str, Any] = {
        "count": len(values),
        "sum": total,
        "average": total / len(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }
    return stats


def summarise_adaptive_articles(
    articles: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Aggregate adaptive crawl telemetry from a sequence of articles.

    Parameters
    ----------
    articles:
        Iterable of article payloads containing Crawl4AI extraction metadata.

    Returns
    -------
    dict | None
        Aggregated telemetry dictionary, or ``None`` when no adaptive payloads
        are detected.
    """

    total_articles = 0
    sufficient_count = 0
    confidence_values: list[float] = []
    pages_crawled_values: list[float] = []
    source_score_values: list[float] = []
    stop_reasons: Counter[str] = Counter()
    coverage_values: dict[str, list[float]] = defaultdict(list)

    for article in articles:
        extraction_metadata = article.get("extraction_metadata")
        if not isinstance(extraction_metadata, Mapping):
            continue
        crawl_meta = extraction_metadata.get("crawl4ai")
        if not isinstance(crawl_meta, Mapping):
            continue
        adaptive = crawl_meta.get("adaptive_run")
        if not isinstance(adaptive, Mapping):
            continue

        total_articles += 1

        if bool(adaptive.get("is_sufficient")):
            sufficient_count += 1

        confidence = _coerce_float(adaptive.get("confidence"))
        if confidence is not None:
            confidence_values.append(confidence)

        pages_crawled = _coerce_float(adaptive.get("pages_crawled"))
        if pages_crawled is not None:
            pages_crawled_values.append(pages_crawled)

        stop_reason = adaptive.get("stop_reason")
        if isinstance(stop_reason, str) and stop_reason:
            stop_reasons[stop_reason] += 1

        source_score = _coerce_float(adaptive.get("source_score"))
        if source_score is not None:
            source_score_values.append(source_score)

        coverage_stats = adaptive.get("coverage_stats")
        if isinstance(coverage_stats, Mapping):
            for key, value in coverage_stats.items():
                coerced = _coerce_float(value)
                if coerced is not None:
                    coverage_values[str(key)].append(coerced)

    if total_articles == 0:
        return None

    summary: dict[str, Any] = {
        "articles": {
            "total": total_articles,
            "sufficient": sufficient_count,
            "insufficient": max(total_articles - sufficient_count, 0),
        },
        "stop_reasons": dict(stop_reasons),
    }

    confidence_stats = _build_stats(confidence_values)
    if confidence_stats["count"]:
        summary["confidence"] = confidence_stats

    pages_stats = _build_stats(pages_crawled_values)
    if pages_stats["count"]:
        summary["pages_crawled"] = pages_stats

    source_stats = _build_stats(source_score_values)
    if source_stats["count"]:
        summary["source_score"] = source_stats

    if coverage_values:
        coverage_summary: dict[str, Any] = {}
        for key, values in coverage_values.items():
            stats = _build_stats(values)
            if stats["count"]:
                coverage_summary[key] = stats
        if coverage_summary:
            summary["coverage_stats"] = coverage_summary

    return summary
