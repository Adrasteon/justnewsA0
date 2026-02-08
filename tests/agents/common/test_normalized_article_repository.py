from __future__ import annotations

from agents.common.agent_chain_harness import NormalizedArticle
from agents.common.normalized_article_repository import (
    ArticleCandidate,
    NormalizedArticleRepository,
)


class _StubCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed = None

    def execute(self, query, params):
        self.executed = (" ".join(query.split()), params)

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _StubConnection:
    def __init__(self, rows):
        self.cursor_instance = _StubCursor(rows)

    def cursor(self, dictionary=True):
        assert dictionary is True
        return self.cursor_instance


class _StubService:
    def __init__(self, rows):
        self.mb_conn = _StubConnection(rows)
        self.ensure_called = False

    def ensure_conn(self):
        self.ensure_called = True


def test_fetch_candidates_builds_articles(monkeypatch):
    rows = [
        {
            "id": 42,
            "url": "https://example.com/story",
            "title": "Example Story",
            "content": "A" * 500,
            "summary": "",
            "metadata": '{"url": "https://example.com/story"}',
            "structured_metadata": '{"title": "Example Story"}',
            "authors": '["Ada"]',
            "publication_date": "2025-12-03",
            "needs_review": False,
            "fact_check_status": None,
        }
    ]
    service = _StubService(rows)
    repo = NormalizedArticleRepository(db_service=service)

    candidates = repo.fetch_candidates(limit=1)

    assert service.ensure_called is True
    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, ArticleCandidate)
    assert isinstance(candidate.article, NormalizedArticle)
    assert candidate.article.article_id == "42"
    assert candidate.article.url == "https://example.com/story"
    assert candidate.article.title == "Example Story"
    assert candidate.article.metadata["authors"] == ["Ada"]

    # Ensure the query filtered by minimum chars and limit placeholder
    _, params = service.mb_conn.cursor_instance.executed
    assert params[0] == 400  # min_chars default
    assert params[-1] == 1  # limit


def test_fetch_candidates_respects_article_ids():
    rows = [
        {
            "id": 5,
            "url": "https://example.com/a",
            "title": "A",
            "content": "B" * 500,
            "summary": "",
            "metadata": None,
            "structured_metadata": None,
            "authors": None,
            "publication_date": None,
            "needs_review": False,
            "fact_check_status": None,
        }
    ]
    service = _StubService(rows)
    repo = NormalizedArticleRepository(db_service=service)

    repo.fetch_candidates(limit=2, article_ids=["5", "9"])

    query, params = service.mb_conn.cursor_instance.executed
    assert "id IN" in query
    # params = [min_chars, id1, id2, limit]
    assert list(params[1:3]) == ["5", "9"]
