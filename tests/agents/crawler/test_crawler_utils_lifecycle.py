from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from agents.crawler import crawler_utils


def test_is_source_row_eligible_blocks_blocked_state():
    assert (
        crawler_utils.is_source_row_eligible_for_crawl(
            {"source_state": "blocked"},
            whitelist_only_mode=False,
            discovery_enabled=True,
            provisional_ingest_enabled=True,
        )
        is False
    )


@pytest.mark.parametrize(
    "state,eligible",
    [
        ("trusted_whitelist", True),
        ("trusted_promoted", True),
        ("probation", True),
        ("provisional_discovered", False),
        ("candidate_review", False),
    ],
)
def test_is_source_row_eligible_respects_whitelist_only_mode(state, eligible):
    assert (
        crawler_utils.is_source_row_eligible_for_crawl(
            {"source_state": state},
            whitelist_only_mode=True,
            discovery_enabled=True,
            provisional_ingest_enabled=True,
        )
        is eligible
    )


def test_is_source_row_eligible_allows_provisional_only_when_discovery_and_provisional_on():
    assert (
        crawler_utils.is_source_row_eligible_for_crawl(
            {"source_state": "provisional_discovered"},
            whitelist_only_mode=False,
            discovery_enabled=True,
            provisional_ingest_enabled=True,
        )
        is True
    )
    assert (
        crawler_utils.is_source_row_eligible_for_crawl(
            {"source_state": "provisional_discovered"},
            whitelist_only_mode=False,
            discovery_enabled=False,
            provisional_ingest_enabled=True,
        )
        is False
    )


def _setup_connection(state_column_supported: bool):
    conn = MagicMock()
    schema_cursor = MagicMock()
    schema_cursor.fetchone.return_value = (
        ("source_state", "varchar(64)", "YES", "", None, "")
        if state_column_supported
        else None
    )

    data_cursor = MagicMock()
    data_cursor.fetchall.return_value = [{"id": 1, "domain": "example.com"}]

    conn.cursor.side_effect = [schema_cursor, data_cursor]
    return conn, data_cursor


@contextmanager
def _as_context(conn):
    yield conn


def test_get_active_sources_uses_trusted_and_provisional_states_when_enabled(monkeypatch):
    conn, data_cursor = _setup_connection(state_column_supported=True)
    monkeypatch.setattr(crawler_utils, "_get_conn", lambda: _as_context(conn))
    monkeypatch.setattr(crawler_utils, "_SOURCE_STATE_COLUMN_SUPPORTED", None)
    monkeypatch.setenv("UNIFIED_CRAWLER_DISCOVERY_ENABLED", "1")
    monkeypatch.setenv("UNIFIED_CRAWLER_PROVISIONAL_INGEST_ENABLED", "1")
    monkeypatch.setenv("UNIFIED_CRAWLER_WHITELIST_ONLY_MODE", "0")

    crawler_utils.get_active_sources(limit=10)

    query, params = data_cursor.execute.call_args[0]
    assert "source_state" in query
    assert "provisional_discovered" in params
    assert "candidate_review" in params


def test_get_active_sources_excludes_provisional_states_in_whitelist_only(monkeypatch):
    conn, data_cursor = _setup_connection(state_column_supported=True)
    monkeypatch.setattr(crawler_utils, "_get_conn", lambda: _as_context(conn))
    monkeypatch.setattr(crawler_utils, "_SOURCE_STATE_COLUMN_SUPPORTED", None)
    monkeypatch.setenv("UNIFIED_CRAWLER_DISCOVERY_ENABLED", "1")
    monkeypatch.setenv("UNIFIED_CRAWLER_PROVISIONAL_INGEST_ENABLED", "1")
    monkeypatch.setenv("UNIFIED_CRAWLER_WHITELIST_ONLY_MODE", "1")

    crawler_utils.get_active_sources(limit=10)

    query, params = data_cursor.execute.call_args[0]
    assert "source_state" in query
    assert "provisional_discovered" not in params
    assert "candidate_review" not in params
