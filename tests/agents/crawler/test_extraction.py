from __future__ import annotations

from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry

import agents.crawler.extraction as extraction
from common.stage_b_metrics import (
    configure_stage_b_metrics,
    use_default_stage_b_metrics,
)


def configure_thresholds(
    monkeypatch, *, min_words: int, min_ratio: float, raw_dir: Path
) -> None:
    monkeypatch.setattr(extraction, "_MIN_WORDS", min_words)
    monkeypatch.setattr(extraction, "_MIN_TEXT_HTML_RATIO", min_ratio)
    monkeypatch.setattr(extraction, "_DEFAULT_RAW_DIR", raw_dir)


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.delenv("ARTICLE_MIN_WORDS", raising=False)
    monkeypatch.delenv("ARTICLE_MIN_TEXT_HTML_RATIO", raising=False)
    monkeypatch.delenv("JUSTNEWS_RAW_HTML_DIR", raising=False)


@pytest.fixture
def stage_b_metrics():
    registry = CollectorRegistry()
    metrics = configure_stage_b_metrics(registry)
    yield metrics
    use_default_stage_b_metrics()


def make_sample_html(title: str, body: str, *, canonical: str | None = None) -> str:
    canonical_link = f"<link rel='canonical' href='{canonical}'>" if canonical else ""
    return (
        "<html><head>"
        f"<title>{title}</title>"
        "<meta name='author' content='Jane Roe'>"
        "<meta property='article:section' content='Science'>"
        "<meta property='article:tag' content='Research,Space'>"
        f"{canonical_link}"
        "</head><body>"
        f"<article><p>{body}</p></article>"
        "</body></html>"
    )


def test_extract_article_content_basic(tmp_path, monkeypatch):
    configure_thresholds(monkeypatch, min_words=10, min_ratio=0.001, raw_dir=tmp_path)

    body = " ".join(["Insightful news content"] * 20)
    html = make_sample_html("Space Update", body, canonical="/science/space-update")
    outcome = extraction.extract_article_content(html, "https://example.com/news/space")

    assert outcome.text.startswith("Insightful news content")
    assert outcome.word_count >= 20
    assert outcome.canonical_url == "https://example.com/science/space-update"
    assert outcome.authors == ["Jane Roe"]
    assert outcome.section == "Science"
    assert sorted(outcome.tags) == ["Research", "Space"]
    assert outcome.needs_review is False
    assert outcome.raw_html_path is not None
    assert Path(outcome.raw_html_path).exists()


def test_extract_article_content_marks_low_quality(tmp_path, monkeypatch):
    configure_thresholds(monkeypatch, min_words=50, min_ratio=0.2, raw_dir=tmp_path)

    html = make_sample_html("Brief Update", "Short" * 2)
    outcome = extraction.extract_article_content(html, "https://example.com/brief")

    assert outcome.needs_review is True
    assert any(
        reason.startswith("word_count_below_threshold")
        for reason in outcome.review_reasons
    )
    assert any(
        reason.startswith("low_text_html_ratio") for reason in outcome.review_reasons
    )


def test_extract_article_records_primary_metrics(
    tmp_path, monkeypatch, stage_b_metrics
):
    configure_thresholds(monkeypatch, min_words=5, min_ratio=0.001, raw_dir=tmp_path)

    def fake_trafilatura(html: str, url: str):
        return {
            "text": " ".join(["headline"] * 20),
            "title": "Primary Article",
            "canonical_url": url,
            "publication_date": None,
            "authors": ["Reporter"],
            "metadata": {},
            "section": "News",
            "language": "en",
            "tags": ["primary"],
        }

    monkeypatch.setattr(extraction, "_extract_with_trafilatura", fake_trafilatura)

    html = make_sample_html("Primary Article", "Quality content" * 20)
    outcome = extraction.extract_article_content(html, "https://example.com/item")

    assert outcome.extractor_used == "trafilatura"
    assert stage_b_metrics.get_extraction_count("trafilatura") == 1.0
    assert stage_b_metrics.get_extraction_count("none") == 0.0
    assert stage_b_metrics.get_fallback_count("readability", "success") == 0.0


def test_extract_article_records_fallback_metrics(
    tmp_path, monkeypatch, stage_b_metrics
):
    configure_thresholds(monkeypatch, min_words=10, min_ratio=0.001, raw_dir=tmp_path)

    monkeypatch.setattr(extraction, "_extract_with_trafilatura", lambda *_: None)

    def fake_readability(html: str):
        return {
            "text": " ".join(["fallback"] * 30),
            "title": "Fallback Article",
        }

    monkeypatch.setattr(extraction, "_extract_with_readability", fake_readability)

    html = make_sample_html("Fallback Article", "Spare content")
    outcome = extraction.extract_article_content(html, "https://example.com/fallback")

    assert outcome.extractor_used == "readability"
    assert stage_b_metrics.get_extraction_count("readability") == 1.0
    assert stage_b_metrics.get_fallback_count("readability", "success") == 1.0
    assert stage_b_metrics.get_fallback_count("readability", "failed") == 0.0
