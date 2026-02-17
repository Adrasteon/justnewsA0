"""Tests for the transparency repository."""

from pathlib import Path

from agents.dashboard.transparency_repository import TransparencyRepository


def _fixture_repo() -> TransparencyRepository:
    project_root = Path(__file__).resolve().parents[3]
    data_dir = project_root / "archive_storage" / "transparency"
    return TransparencyRepository(data_dir)


def test_status_counts():
    repo = _fixture_repo()
    status = repo.get_status()
    assert status["counts"]["facts"] >= 1
    assert status["counts"]["evidence"] >= 1
    assert status["integrity"]["status"] in {"ok", "degraded"}


def test_get_fact_includes_joins():
    repo = _fixture_repo()
    fact_id = "fact-2025-10-25-ap-election-001"
    payload = repo.get_fact(fact_id)
    assert payload["fact"]["fact_id"] == fact_id
    assert payload["article"]["article_id"] == payload["fact"]["article_id"]
    assert payload["cluster"]["cluster_id"] == payload["fact"]["cluster_id"]
    assert payload["evidence"], "Expected evidence payloads to be returned"
