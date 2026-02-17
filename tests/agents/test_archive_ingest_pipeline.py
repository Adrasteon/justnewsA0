from __future__ import annotations

import copy

import pytest

from agents.archive.ingest_pipeline import queue_article


def _base_payload() -> dict:
    return {
        "job_id": "job-123",
        "candidate_id": "cand-456",
        "label_id": "label-789",
        "label": "publishable",
        "needs_cleanup": False,
        "annotator_id": "annotator-1",
        "created_at": "2025-12-02T12:30:00Z",
        "cleaned_text": "  Final curated content body.  ",
        "candidate": {
            "id": "cand-456",
            "url": "https://Example.com/story?id=123&utm_source=newsletter",
            "site_id": "123",
            "extracted_title": "Breaking News",
            "extracted_text": "Original content",
            "raw_html_ref": "raw_html/2025/12/02/cand-456.html",
            "candidate_ts": "2025-12-02T12:00:00Z",
            "crawler_job_id": "crawl-001",
            "features": {
                "language": "en",
                "tags": ["tag1", "tag2"],
                "authors": ["Jane Doe"],
                "publication_date": "2025-12-01T12:00:00Z",
                "word_count": 450,
                "confidence": 0.9,
                "paywall_flag": False,
            },
        },
    }


def test_queue_article_forwarding(monkeypatch):
    recorded: dict[str, dict] = {}

    def fake_save_article(content: str, metadata: dict, *_args, **_kwargs):
        recorded["content"] = content
        recorded["metadata"] = metadata
        return {"status": "success", "article_id": 42}

    monkeypatch.setattr(
        "agents.archive.ingest_pipeline.save_article", fake_save_article
    )

    payload = _base_payload()
    result = queue_article(copy.deepcopy(payload))

    assert result["article_id"] == 42
    assert recorded["content"] == payload["cleaned_text"].strip()
    assert recorded["metadata"]["normalized_url"] == "https://example.com/story?id=123"
    assert recorded["metadata"]["source_id"] == 123
    assert result["job_id"] == payload["job_id"]


def test_queue_article_requires_candidate():
    with pytest.raises(ValueError):
        queue_article({})


def test_queue_article_falls_back_to_extracted_text(monkeypatch):
    captured: dict[str, str] = {}

    def fake_save_article(content: str, metadata: dict, *_args, **_kwargs):
        captured["content"] = content
        return {"status": "success", "article_id": 77}

    monkeypatch.setattr(
        "agents.archive.ingest_pipeline.save_article", fake_save_article
    )

    payload = _base_payload()
    payload.pop("cleaned_text", None)
    payload["candidate"]["extracted_text"] = " extractor content "

    result = queue_article(payload)

    assert result["article_id"] == 77
    assert captured["content"] == "extractor content"


def test_queue_article_missing_content(monkeypatch):
    payload = _base_payload()
    payload.pop("cleaned_text", None)
    payload["candidate"].pop("extracted_text", None)

    with pytest.raises(ValueError):
        queue_article(payload)
