from __future__ import annotations

from pathlib import Path

import pytest

import agents.crawler.extraction as extraction
from agents.sites.generic_site_crawler import GenericSiteCrawler, SiteConfig
from common.url_normalization import hash_article_url, normalize_article_url


@pytest.fixture(autouse=True)
def reset_env(monkeypatch, tmp_path):
    monkeypatch.delenv("JUSTNEWS_RAW_HTML_DIR", raising=False)
    monkeypatch.delenv("ARTICLE_MIN_WORDS", raising=False)
    monkeypatch.delenv("ARTICLE_MIN_TEXT_HTML_RATIO", raising=False)
    monkeypatch.delenv("ARTICLE_URL_HASH_ALGO", raising=False)
    monkeypatch.delenv("ARTICLE_URL_NORMALIZATION", raising=False)
    monkeypatch.setattr(extraction, "_DEFAULT_RAW_DIR", tmp_path)
    monkeypatch.setattr(extraction, "_MIN_WORDS", 5)
    monkeypatch.setattr(extraction, "_MIN_TEXT_HTML_RATIO", 0.001)


def make_site_config() -> SiteConfig:
    return SiteConfig(
        {
            "id": 42,
            "name": "Example News",
            "domain": "example.com",
            "url": "https://example.com",
            "metadata": {"crawling_strategy": "generic"},
        }
    )


def make_html() -> str:
    body = " ".join(["Informative" for _ in range(30)])
    return (
        "<html><head><title>Focus Story</title>"
        "<meta name='author' content='Alex Doe'>"
        "<meta property='article:tag' content='Policy,Economy'>"
        "<meta property='article:section' content='Business'>"
        "<link rel='canonical' href='https://example.com/business/focus-story'>"
        "</head><body><p>"
        f"{body}"
        "</p></body></html>"
    )


def test_build_article_enriches_metadata(tmp_path):
    config = make_site_config()
    crawler = GenericSiteCrawler(config, enable_http_fetch=False)

    article = crawler._build_article("https://example.com/news/focus", make_html())

    assert article is not None
    assert article["title"] == "Focus Story"
    assert article["canonical"] == "https://example.com/business/focus-story"
    assert article["language"] in {None, "en"}
    assert article["authors"] == ["Alex Doe"]
    assert article["section"] == "Business"
    assert sorted(article["tags"]) == ["Economy", "Policy"]
    assert article["needs_review"] is False
    assert article["raw_html_ref"] is not None
    assert Path(article["raw_html_ref"]).exists()
    assert article["normalized_url"] == normalize_article_url(
        "https://example.com/news/focus", article["canonical"]
    )

    expected_hash = hash_article_url(article["normalized_url"], algorithm="sha256")
    assert article["url_hash"] == expected_hash
    assert article["url_hash_algorithm"] == "sha256"


def test_build_article_respects_review_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(extraction, "_MIN_WORDS", 200)
    config = make_site_config()
    crawler = GenericSiteCrawler(config, enable_http_fetch=False)

    article = crawler._build_article("https://example.com/news/focus", make_html())

    assert article is not None
    assert article["needs_review"] is True
    assert "word_count_below_threshold" in "".join(
        article["extraction_metadata"]["review_reasons"]
    )
