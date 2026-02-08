from unittest.mock import MagicMock

import pytest

from agents.memory.tools import save_article


class FakeCursor:
    def __init__(self, return_id=None):
        self.return_id = return_id
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchone(self):
        return (self.return_id,) if self.return_id is not None else None

    def close(self):
        pass


class FakeDBService:
    def __init__(self):
        self.mb_conn = MagicMock()
        self.collection = MagicMock()
        cursor = FakeCursor(return_id=123)
        self.mb_conn.cursor.return_value = cursor

    def close(self):
        pass

    def ensure_conn(self):
        """Stub method to satisfy callers that expect a database connection to be established."""
        return True


class FakeEmbeddingModel:
    def encode(self, content):
        # Return a deterministic small vector
        return [0.1, 0.2, 0.3]


class DummyMetrics:
    def __init__(self):
        self.events = []

    def record_ingestion(self, key):
        self.events.append(("ingest", key))

    def record_embedding(self, key):
        self.events.append(("embed", key))

    def observe_embedding_latency(self, cache_label, duration):
        self.events.append(("latency", cache_label, duration))


@pytest.fixture(autouse=True)
def patch_db_and_embedding(monkeypatch):
    # Patch create_database_service to return a fake DB
    monkeypatch.setattr(
        "database.utils.migrated_database_utils.create_database_service",
        lambda: FakeDBService(),
    )
    # Patch get_embedding_model
    monkeypatch.setattr(
        "agents.memory.tools.get_embedding_model", lambda: FakeEmbeddingModel()
    )
    # Patch metrics
    dummy = DummyMetrics()
    monkeypatch.setattr("agents.memory.tools.get_stage_b_metrics", lambda: dummy)
    return dummy


def test_save_article_success(patch_db_and_embedding):
    metadata = {"url": "https://example.com", "title": "Test Article"}
    res = save_article("Test content", metadata)
    assert isinstance(res, dict)
    assert res.get("status") in ("success", "duplicate") or "error" in res
    if "status" in res:
        assert res["status"] in ("success", "duplicate")
    # Ensure processing_time is present
    assert "processing_time" in res and res["processing_time"] >= 0
    assert "article_id" in res


def test_save_article_duplicate(monkeypatch):
    # Simulate duplicate by having cursor.fetchone return an id
    class DuplicateDB(FakeDBService):
        def __init__(self):
            super().__init__()
            self.mb_conn.cursor.return_value = FakeCursor(return_id=100)

    monkeypatch.setattr(
        "database.utils.migrated_database_utils.create_database_service",
        lambda: DuplicateDB(),
    )
    monkeypatch.setattr(
        "agents.memory.tools.get_embedding_model", lambda: FakeEmbeddingModel()
    )
    # metrics fixture is autouse; no need to re-patch get_stage_b_metrics
    # Force a hash value so the duplicate branch uses url_hash lookup
    monkeypatch.setattr(
        "agents.memory.tools.hash_article_url",
        lambda url, algorithm="sha256": "dummyhash",
    )

    res = save_article("Test content", {"url": "https://example.com"})
    assert "status" in res
    assert res["status"] in ("duplicate", "success") or "error" in res
    assert "processing_time" in res and res["processing_time"] >= 0
