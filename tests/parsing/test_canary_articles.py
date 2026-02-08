from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from prometheus_client import CollectorRegistry

import agents.crawler.extraction as extraction
from common.stage_b_metrics import (
    configure_stage_b_metrics,
    use_default_stage_b_metrics,
)

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "canary_articles"


def _load_canary_cases() -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    if not FIXTURE_ROOT.exists():
        return cases
    for manifest_path in sorted(FIXTURE_ROOT.glob("*/expected.json")):
        expected = json.loads(manifest_path.read_text())
        html = (manifest_path.parent / "raw.html").read_text()
        cases.append(
            {
                "id": expected.get("id", manifest_path.parent.name),
                "html": html,
                "expected": expected,
            }
        )
    return cases


CANARY_CASES = _load_canary_cases()
CASE_IDS = [case["id"] for case in CANARY_CASES]


def _normalise_text(value: str) -> str:
    return " ".join(value.split())


@pytest.fixture(autouse=True)
def isolate_stage_b_metrics():
    registry = CollectorRegistry()
    configure_stage_b_metrics(registry)
    yield
    use_default_stage_b_metrics()


@pytest.mark.parametrize("case", CANARY_CASES, ids=CASE_IDS)
def test_canary_articles_match_snapshots(case, tmp_path, monkeypatch):
    if not case:
        pytest.skip("No canary fixtures available")

    expected = case["expected"]
    html = case["html"]

    monkeypatch.setattr(extraction, "_DEFAULT_RAW_DIR", tmp_path)

    outcome = extraction.extract_article_content(html, expected["url"])
    normalised_text = _normalise_text(outcome.text)

    assert normalised_text, "extraction produced empty text"
    assert outcome.title == expected["title"]
    assert outcome.word_count == expected["word_count"]
    assert outcome.needs_review == expected["needs_review"]
    assert outcome.canonical_url == expected["canonical_url"]

    digest = hashlib.sha256(normalised_text.encode("utf-8")).hexdigest()
    assert digest == expected["text_hash"], f"text mismatch for {expected['id']}"
    assert expected["text_preview"] in normalised_text

    expected_extractor = expected.get("extraction_used")
    if expected_extractor:
        assert outcome.extractor_used == expected_extractor
