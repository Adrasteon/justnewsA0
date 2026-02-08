"""Tests for the ClusterFetcher: ensures cluster membership resolution and DB fetches work."""

import pytest

from agents.cluster_fetcher.cluster_fetcher import ClusterFetcher

pytestmark = pytest.mark.database


def make_db_row(article_id, title, content, url, metadata=None):
    return {
        "id": article_id,
        "title": title,
        "content": content,
        "url": url,
        "metadata": metadata or {},
    }


def test_fetch_cluster_by_article_ids():
    # Prepare a simple mocked DB service and cursor
    from unittest.mock import MagicMock

    mock_cursor = MagicMock()
    row = make_db_row("a1", "T1", "Content 1", "https://example.com/1", {"k": "v"})
    mock_cursor.fetchone.return_value = row

    fake_db = MagicMock()
    fake_db.mb_conn.cursor.return_value = mock_cursor

    fetcher = ClusterFetcher(db_service=fake_db)

    # Pass a list of article ids to fetch
    results = fetcher.fetch_cluster(article_ids=["a1"])

    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0].article_id == "a1"
    assert "Content 1" in results[0].content
    assert results[0].url == "https://example.com/1"


def test_fetch_cluster_by_cluster_id_uses_transparency_repo():
    # Transparency sample cluster is provided in archive_storage/transparency
    cluster_id = "cluster-2025-10-election-security-001"

    # Prepare two DB rows in sequence for two article ids found in the transparency cluster
    from unittest.mock import MagicMock

    mock_cursor = MagicMock()
    row1 = make_db_row(
        "article-2025-10-25-ap-001", "AP 1", "AP Content", "https://apnews.com/a"
    )
    row2 = make_db_row(
        "article-2025-10-24-reuters-003",
        "Reuters 1",
        "Reuters Content",
        "https://www.reuters.com/r",
    )

    # Simulate sequential fetchone() returns
    mock_cursor.fetchone.side_effect = [row1, row2]

    fake_db = MagicMock()
    fake_db.mb_conn.cursor.return_value = mock_cursor

    fetcher = ClusterFetcher(db_service=fake_db)

    results = fetcher.fetch_cluster(cluster_id=cluster_id)

    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0].article_id == "article-2025-10-25-ap-001"
    assert results[1].url.startswith("https://www.reuters.com")


def test_fetch_cluster_deduplication_by_url():
    from unittest.mock import MagicMock

    mock_cursor = MagicMock()

    # Two rows with the same URL should result in one record after dedupe
    row1 = make_db_row("a1", "T1", "Content 1", "https://example.com/1")
    row2 = make_db_row("a2", "T2", "Content 2", "https://example.com/1")
    mock_cursor.fetchone.side_effect = [row1, row2]

    fake_db = MagicMock()
    fake_db.mb_conn.cursor.return_value = mock_cursor

    fetcher = ClusterFetcher(db_service=fake_db)

    results = fetcher.fetch_cluster(article_ids=["a1", "a2"])

    assert len(results) == 1
    assert results[0].url == "https://example.com/1"
