from agents.memory.tools import save_article


def test_save_article_fails_when_chroma_required(monkeypatch):
    # Create the environment where CHROMADB_REQUIRE_CANONICAL is enabled but no chroma collection
    monkeypatch.setenv("CHROMADB_REQUIRE_CANONICAL", "1")
    monkeypatch.setenv("CHROMADB_CANONICAL_HOST", "localhost")
    monkeypatch.setenv("CHROMADB_CANONICAL_PORT", "3307")
    # Set host to something that is not the canonical Chroma (force a mismatch)
    monkeypatch.setenv("CHROMADB_HOST", "localhost")
    # Use a non-canonical port to simulate a mismatch (do not use 8000)
    monkeypatch.setenv("CHROMADB_PORT", "3310")

    # Patch to return a fake DB service with no Chroma collection to trigger the error
    from unittest.mock import MagicMock

    class MockDB:
        def __init__(self):
            self.mb_conn = MagicMock()
            self.collection = None

        def ensure_conn(self):
            return True

        def close(self):
            return None

    monkeypatch.setattr(
        "database.utils.migrated_database_utils.create_database_service",
        lambda: MockDB(),
    )
    # Patch embedding model to a stub
    monkeypatch.setattr("agents.memory.tools.get_embedding_model", lambda: None)

    res = save_article("Some test content", {"url": "https://test.invalid/"})
    assert res.get("error") is not None
    assert (
        "chroma" in res.get("error")
        or "Host/port mismatch" in res.get("error")
        or "MySQL" in res.get("error")
    )
