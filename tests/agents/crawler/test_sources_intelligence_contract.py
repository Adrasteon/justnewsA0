from contextlib import contextmanager
from unittest.mock import MagicMock

from agents.crawler import crawler_utils


@contextmanager
def _as_context(conn):
    yield conn


def test_record_source_crawl_outcome_writes_only_lean_fields(monkeypatch):
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor

    monkeypatch.setattr(crawler_utils, '_get_conn', lambda: _as_context(conn))

    crawler_utils.record_source_crawl_outcome(
        source_id=17,
        domain='example.com',
        attempted=9,
        ingested=0,
        errors=1,
        paywalls=0,
        blocked=True,
    )

    query, _params = cursor.execute.call_args[0]
    lowered = query.lower()

    assert 'last_crawl_outcome' in lowered
    assert 'last_candidate_count' in lowered
    assert 'crawl_fail_streak' in lowered
    assert 'crawl_blocked_until' in lowered
    assert 'crawl_quality_score' in lowered

    # Guardrail: no high-cardinality blobs should be persisted in sources updates.
    assert ' metadata ' not in lowered


def test_record_source_crawl_outcome_blocked_classification(monkeypatch):
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor

    monkeypatch.setattr(crawler_utils, '_get_conn', lambda: _as_context(conn))

    crawler_utils.record_source_crawl_outcome(
        source_id=99,
        domain='blocked.example',
        attempted=4,
        ingested=0,
        errors=2,
        paywalls=0,
        blocked=True,
    )

    _query, params = cursor.execute.call_args[0]
    assert params[0] == 'blocked'
