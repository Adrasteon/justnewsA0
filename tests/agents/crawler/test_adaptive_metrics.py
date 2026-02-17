import pytest

from agents.crawler.adaptive_metrics import summarise_adaptive_articles


def test_no_adaptive_payloads_returns_none():
    articles = [
        {"id": "a1", "extraction_metadata": {}},
        {"id": "a2"},
    ]

    result = summarise_adaptive_articles(articles)
    assert result is None


def test_summarise_basic_adaptive_payloads():
    articles = [
        {
            "id": "a1",
            "extraction_metadata": {
                "crawl4ai": {
                    "adaptive_run": {
                        "is_sufficient": True,
                        "confidence": 0.87,
                        "pages_crawled": 3,
                        "stop_reason": "sufficient",
                        "source_score": 0.8,
                        "coverage_stats": {"title": 1.0, "body": 0.95},
                    }
                }
            },
        },
        {
            "id": "a2",
            "extraction_metadata": {
                "crawl4ai": {
                    "adaptive_run": {
                        "is_sufficient": False,
                        "confidence": 0.6,
                        "pages_crawled": 5,
                        "stop_reason": "max_pages",
                        "source_score": 0.5,
                        "coverage_stats": {"title": 0.9, "body": 0.5},
                    }
                }
            },
        },
    ]

    summary = summarise_adaptive_articles(articles)
    assert summary is not None
    assert summary["articles"]["total"] == 2
    assert summary["articles"]["sufficient"] == 1
    assert summary["articles"]["insufficient"] == 1

    # confidence stats present and aggregated
    assert "confidence" in summary
    assert summary["confidence"]["count"] == 2
    assert pytest.approx(summary["confidence"]["average"], rel=1e-3) == (0.87 + 0.6) / 2

    # pages crawled aggregated
    assert "pages_crawled" in summary
    assert summary["pages_crawled"]["count"] == 2

    # stop reasons counted
    assert summary["stop_reasons"]["sufficient"] == 1
    assert summary["stop_reasons"]["max_pages"] == 1

    # coverage stats present for keys
    assert "coverage_stats" in summary
    assert "title" in summary["coverage_stats"]
    assert summary["coverage_stats"]["title"]["count"] == 2
