"""High-precision extraction pipeline for the Stage B ingestion scheduler.

This module centralises text extraction, metadata parsing, and governance
heuristics so that crawler components can reuse a single, well-instrumented
implementation.  The goal is to deliver clean article bodies with provenance,
while keeping enough context (raw HTML + structured metadata) for audits and
reprocessing.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from common.json_utils import make_json_safe
from common.observability import get_logger
from common.stage_b_metrics import get_stage_b_metrics

logger = get_logger(__name__)

try:  # Optional dependency; graceful degradation when unavailable
    import trafilatura  # type: ignore[import-not-found]
    from trafilatura.metadata import (
        extract_metadata as _trafilatura_extract_metadata,  # type: ignore[attr-defined, import-not-found]
    )
except ImportError:  # pragma: no cover - missing dependency handled at runtime
    trafilatura = None
    _trafilatura_extract_metadata = None

try:  # readability-lxml (HTML → Article fallback)
    from lxml import html as lxml_html  # type: ignore[import-not-found]
    from readability import (
        Document as ReadabilityDocument,  # type: ignore[import-not-found]
    )
except ImportError:  # pragma: no cover
    ReadabilityDocument = None
    lxml_html = None

try:
    import justext  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    justext = None

try:
    import extruct  # type: ignore[import-not-found]
    from w3lib.html import get_base_url  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    extruct = None
    get_base_url = None

try:
    from langdetect import (  # type: ignore[import-not-found]
        DetectorFactory,
        LangDetectException,
    )
    from langdetect import detect as detect_language

    DetectorFactory.seed = 42
except ImportError:  # pragma: no cover
    DetectorFactory = None
    LangDetectException = Exception
    detect_language = None

# Shared JSON-sanitising helper

# Heuristic thresholds (configurable via env)
_MIN_WORDS = int(os.environ.get("ARTICLE_MIN_WORDS", "120"))
_MIN_TEXT_HTML_RATIO = float(os.environ.get("ARTICLE_MIN_TEXT_HTML_RATIO", "0.015"))

_SERVICE_DIR = Path(os.environ.get("SERVICE_DIR", Path(__file__).resolve().parents[2]))
_DEFAULT_RAW_DIR = Path(
    os.environ.get(
        "JUSTNEWS_RAW_HTML_DIR",
        _SERVICE_DIR / "archive_storage" / "raw_html",
    )
)


@dataclass
class ExtractionOutcome:
    """Structured response describing an article extraction attempt."""

    text: str = ""
    title: str = ""
    canonical_url: str | None = None
    publication_date: str | None = None
    authors: list[str] = field(default_factory=list)
    section: str | None = None
    tags: list[str] = field(default_factory=list)
    language: str | None = None
    extractor_used: str | None = None
    fallbacks_attempted: list[str] = field(default_factory=list)
    word_count: int = 0
    boilerplate_ratio: float = 0.0
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    structured_metadata: dict[str, Any] = field(default_factory=dict)
    raw_html_path: str | None = None


def _store_raw_html(
    html: str, url: str, *, target_dir: Path = _DEFAULT_RAW_DIR
) -> str | None:
    """Persist the raw HTML to disk for forensic reprocessing."""

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        digest = hashlib.sha256(url.encode("utf-8", errors="ignore")).hexdigest()[:16]
        filename = f"{timestamp}_{digest}_{uuid.uuid4().hex[:12]}.html"
        file_path = target_dir / filename
        file_path.write_text(html, encoding="utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - best-effort persistence
        logger.warning("Failed to persist raw HTML for %s: %s", url, exc)
        return None

    try:
        relative = file_path.relative_to(_SERVICE_DIR)
        return str(relative)
    except ValueError:
        return str(file_path)


def _extract_with_trafilatura(html: str, url: str) -> dict[str, Any] | None:
    if trafilatura is None or _trafilatura_extract_metadata is None:
        return None
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            target_language=None,
            output_format="txt",
            fast=True,
        )
        if not text:
            return None
        try:
            meta_obj = _trafilatura_extract_metadata(html, default_url=url)
        except TypeError:
            # Older versions expect the keyword 'url'; keep backward compatibility.
            meta_obj = _trafilatura_extract_metadata(html, url=url)
        if meta_obj is None:
            meta_dict: dict[str, Any] = {}
        else:
            try:
                meta_dict = meta_obj.to_dict()  # type: ignore[attr-defined]
            except AttributeError:
                meta_dict = {
                    key: getattr(meta_obj, key)
                    for key in dir(meta_obj)
                    if not key.startswith("_") and not callable(getattr(meta_obj, key))
                }
        title = meta_dict.get("headline") or meta_dict.get("title") or ""
        canonical = meta_dict.get("canonical-url")
        publication_date = meta_dict.get("date") or meta_dict.get("date-publish")
        authors = meta_dict.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        return {
            "text": text,
            "title": title,
            "canonical_url": canonical,
            "publication_date": publication_date,
            "authors": authors,
            "metadata": meta_dict,
            "section": meta_dict.get("section"),
            "language": meta_dict.get("lang"),
            "tags": meta_dict.get("keywords") or [],
        }
    except Exception as exc:  # pragma: no cover - extraction failure
        logger.debug("Trafilatura extraction failed for %s: %s", url, exc)
        return None


def _extract_with_readability(html: str) -> dict[str, Any] | None:
    if ReadabilityDocument is None or lxml_html is None:
        return None
    try:
        doc = ReadabilityDocument(html)
        summary_html = doc.summary(html_partial=True)
        tree = lxml_html.fromstring(summary_html)
        text = tree.text_content().strip()
        title = doc.short_title() or ""
        return {"text": text, "title": title}
    except Exception as exc:  # pragma: no cover
        logger.debug("Readability extraction failed: %s", exc)
        return None


def _extract_with_justext(html: str, language_hint: str | None) -> str | None:
    if justext is None:
        return None
    try:
        stoplist_name = language_hint.capitalize() if language_hint else "English"
        stoplist = justext.get_stoplist(stoplist_name)
    except Exception:
        stoplist = justext.get_stoplist("English")
    try:
        paragraphs = justext.justext(html, stoplist)
        text = "\n".join(p.text for p in paragraphs if not p.is_boilerplate).strip()
        return text or None
    except Exception as exc:  # pragma: no cover
        logger.debug("jusText extraction failed: %s", exc)
        return None


def _plain_text_fallback(html: str) -> str | None:
    """Very lightweight HTML-to-text fallback used when specialized libraries are unavailable."""

    cleaned = re.sub(
        r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(
        r"<style[^>]*>.*?</style>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE
    )
    cleaned = re.sub(r"<!--.*?-->", " ", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip() or None


def _parse_structured_metadata(html: str, url: str) -> dict[str, Any]:
    if extruct is None or get_base_url is None:
        return {}
    try:
        base_url = get_base_url(html, url)
        data = extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["json-ld", "microdata", "opengraph", "dublincore"],
            uniform=True,
        )
        return data
    except Exception as exc:  # pragma: no cover
        logger.debug("Structured metadata extraction failed for %s: %s", url, exc)
        return {}


def _derive_meta_from_dom(html: str, url: str) -> dict[str, Any]:
    if lxml_html is None:
        return {}
    try:
        tree = lxml_html.fromstring(html)
    except Exception as exc:  # pragma: no cover
        logger.debug("Failed to parse HTML DOM for metadata: %s", exc)
        return {}

    canonical = tree.xpath("//link[@rel='canonical']/@href")
    meta_author = tree.xpath(
        "//meta[@name='author']/@content | //meta[@property='article:author']/@content"
    )
    meta_section = tree.xpath("//meta[@property='article:section']/@content")
    meta_tags = tree.xpath(
        "//meta[@property='article:tag']/@content | //meta[@name='keywords']/@content"
    )
    meta_pub = tree.xpath(
        "//meta[@property='article:published_time']/@content | "
        "//meta[@name='date']/@content | //meta[@property='og:published_time']/@content"
    )
    og_url = tree.xpath("//meta[@property='og:url']/@content")

    tags: list[str] = []
    if meta_tags:
        for entry in meta_tags:
            if entry:
                tags.extend(
                    [token.strip() for token in entry.split(",") if token.strip()]
                )

    canonical_url = canonical[0] if canonical else (og_url[0] if og_url else None)
    if canonical_url:
        canonical_url = urljoin(url, canonical_url.strip())

    return {
        "canonical_url": canonical_url,
        "authors": [a.strip() for a in meta_author if a.strip()][:5],
        "section": meta_section[0].strip() if meta_section else None,
        "tags": tags,
        "publication_date": meta_pub[0].strip() if meta_pub else None,
    }


def _normalise_value_sequence(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def extract_article_content(html: str, url: str) -> ExtractionOutcome:
    """Execute the multi-tier extraction pipeline and return a rich outcome."""

    metrics = get_stage_b_metrics()
    outcome = ExtractionOutcome()
    outcome.raw_html_path = _store_raw_html(html, url)

    # Tier 1: Trafilatura
    trafilatura_result = _extract_with_trafilatura(html, url)
    if trafilatura_result:
        outcome.extractor_used = "trafilatura"
        outcome.text = trafilatura_result.get("text", "").strip()
        outcome.title = trafilatura_result.get("title", "")
        outcome.canonical_url = trafilatura_result.get("canonical_url")
        outcome.publication_date = trafilatura_result.get("publication_date")
        outcome.authors = _normalise_value_sequence(trafilatura_result.get("authors"))
        outcome.metadata = trafilatura_result.get("metadata", {})
        outcome.section = trafilatura_result.get("section")
        outcome.language = trafilatura_result.get("language")
        outcome.tags = _normalise_value_sequence(trafilatura_result.get("tags"))
    else:
        outcome.fallbacks_attempted.append("trafilatura")

    # Tier 2: Readability fallback (improves short Trafilatura results or fills gaps)
    if (not outcome.text or len(outcome.text.split()) < _MIN_WORDS) and html:
        readability_result = _extract_with_readability(html)
        if readability_result and readability_result.get("text"):
            if not outcome.text:
                outcome.text = readability_result["text"].strip()
                outcome.extractor_used = outcome.extractor_used or "readability"
            elif len(outcome.text.split()) < len(readability_result["text"].split()):
                outcome.text = readability_result["text"].strip()
                outcome.extractor_used = "readability"
            if not outcome.title:
                outcome.title = readability_result.get("title", "")
            metrics.record_fallback("readability", "success")
        else:
            outcome.fallbacks_attempted.append("readability")
            metrics.record_fallback("readability", "failed")

    # Tier 3: jusText fallback for stubborn pages
    if not outcome.text and html:
        language_hint = outcome.language or (
            outcome.metadata.get("lang") if outcome.metadata else None
        )
        justext_result = _extract_with_justext(html, language_hint)
        if justext_result:
            outcome.text = justext_result.strip()
            outcome.extractor_used = outcome.extractor_used or "justext"
            metrics.record_fallback("justext", "success")
        else:
            outcome.fallbacks_attempted.append("justext")
            metrics.record_fallback("justext", "failed")

    # Tier 4: Plain-text sanitiser as a last resort
    if not outcome.text and html:
        plain_fallback = _plain_text_fallback(html)
        if plain_fallback:
            outcome.text = plain_fallback
            outcome.extractor_used = outcome.extractor_used or "plain_sanitiser"
            metrics.record_fallback("plain_sanitiser", "success")
        else:
            outcome.fallbacks_attempted.append("plain_sanitiser")
            metrics.record_fallback("plain_sanitiser", "failed")

    # Structured metadata and DOM-derived hints
    outcome.structured_metadata = _parse_structured_metadata(html, url)
    dom_meta = _derive_meta_from_dom(html, url)
    if dom_meta:
        outcome.canonical_url = outcome.canonical_url or dom_meta.get("canonical_url")
        if not outcome.publication_date:
            outcome.publication_date = dom_meta.get("publication_date")
        if not outcome.authors:
            outcome.authors = dom_meta.get("authors", [])
        if not outcome.section:
            outcome.section = dom_meta.get("section")
        if not outcome.tags:
            outcome.tags = dom_meta.get("tags", [])

    # Derive language if missing
    if not outcome.language and detect_language and outcome.text:
        try:
            outcome.language = detect_language(outcome.text)
        except LangDetectException:
            outcome.language = None

    outcome.metadata = make_json_safe(outcome.metadata)
    outcome.structured_metadata = make_json_safe(outcome.structured_metadata)

    # Heuristics
    outcome.word_count = len(outcome.text.split()) if outcome.text else 0
    outcome.boilerplate_ratio = (
        len(outcome.text) / max(len(html), 1) if outcome.text and html else 0.0
    )
    if outcome.word_count < _MIN_WORDS:
        outcome.needs_review = True
        outcome.review_reasons.append(f"word_count_below_threshold<{_MIN_WORDS}>")
    if outcome.boilerplate_ratio < _MIN_TEXT_HTML_RATIO:
        outcome.needs_review = True
        outcome.review_reasons.append(f"low_text_html_ratio<{_MIN_TEXT_HTML_RATIO}>")
    if outcome.text and "lorem ipsum" in outcome.text.lower():
        outcome.needs_review = True
        outcome.review_reasons.append("possible_placeholder_text")

    metrics.record_extraction(outcome.extractor_used or "none")
    return outcome
