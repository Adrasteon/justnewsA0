from unittest.mock import MagicMock, patch

from database.utils.migrated_database_utils import (
    close_cached_service,
    create_database_service,
)


def test_create_database_service_caching(monkeypatch):
    # Ensure canonical Chroma so service creation can succeed (use monkeypatch to avoid env bleed)
    monkeypatch.setenv("CHROMADB_REQUIRE_CANONICAL", "1")
    monkeypatch.setenv("CHROMADB_CANONICAL_HOST", "localhost")
    monkeypatch.setenv("CHROMADB_CANONICAL_PORT", "3307")
    monkeypatch.setenv("CHROMADB_HOST", "localhost")
    monkeypatch.setenv("CHROMADB_PORT", "3307")

    # Patch connectors so service creation can succeed without real DBs
    with (
        patch("mysql.connector.connect", return_value=MagicMock()),
        patch("chromadb.HttpClient", return_value=MagicMock()),
        patch("database.utils.chromadb_utils.validate_chroma_is_canonical", return_value={"ok": True}),
    ):
        # Create a service; subsequent calls should return the same cached instance
        s1 = create_database_service()
        s2 = create_database_service()
    assert s1 is s2
    # Clean up
    close_cached_service()
