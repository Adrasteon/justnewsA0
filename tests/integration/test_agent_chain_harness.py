from __future__ import annotations

import json
from pathlib import Path

import pytest

import agents.crawler.extraction as extraction
from agents.common.agent_chain_harness import AgentChainHarness, NormalizedArticle

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "canary_articles"
CANARY_IDS = sorted(p.name for p in FIXTURE_ROOT.iterdir() if p.is_dir())


def _load_article(slug: str) -> NormalizedArticle:
    fixture_dir = FIXTURE_ROOT / slug
    expected = json.loads((fixture_dir / "expected.json").read_text())
    html = (fixture_dir / "raw.html").read_text()
    outcome = extraction.extract_article_content(html, expected["url"])
    article = NormalizedArticle(
        article_id=slug,
        url=expected["url"],
        title=expected["title"],
        text=outcome.text,
        metadata={
            "expected": expected,
            "word_count": outcome.word_count,
            "needs_review": outcome.needs_review,
        },
    )
    return article


@pytest.mark.parametrize("slug", CANARY_IDS)
def test_agent_chain_harness_runs_full_adapter_loop(slug, monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")
    monkeypatch.setenv("FACT_CHECKER_DISABLE_MISTRAL", "0")
    monkeypatch.setattr(extraction, "_DEFAULT_RAW_DIR", tmp_path)

    article = _load_article(slug)
    assert article.text, "extraction returned empty text"

    harness = AgentChainHarness()
    result = harness.run_article(article)

    assert result.article_id == slug
    assert 0.0 <= result.acceptance_score <= 1.0
    assert isinstance(result.needs_followup, bool)
    assert result.story_brief is not None
    assert "summary" in result.story_brief
    assert result.draft is not None
    assert "summary" in result.draft

    if result.fact_checks:
        for check in result.fact_checks:
            assert check["claim"].strip()
            assert check["verdict"] in {"verified", "refuted", "unclear"}
            assert 0.0 <= check["confidence"] <= 1.0
