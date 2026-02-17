import pytest

from database.utils.chromadb_utils import ChromaCanonicalValidationError
from database.utils.migrated_database_utils import create_database_service


def test_chroma_canonical_enforcement(tmp_path, monkeypatch):
    # Set a mismatched CHROMADB host/port while canonical expects a different port
    monkeypatch.setenv("CHROMADB_REQUIRE_CANONICAL", "1")
    monkeypatch.setenv("CHROMADB_CANONICAL_HOST", "localhost")
    monkeypatch.setenv("CHROMADB_CANONICAL_PORT", "3307")
    monkeypatch.setenv("CHROMADB_HOST", "localhost")
    # Use a non-canonical port for the test (avoid using 8000)
    monkeypatch.setenv("CHROMADB_PORT", "3310")

    # Provide a fake MariaDB connection to avoid the top-level test harness's
    # 'mysql.connector.connect' replacement that raises by default. The test
    # only needs a minimal connection to reach the Chroma validation logic.
    from unittest.mock import MagicMock, patch

    # ensure any cached service instance is cleared so create_database_service runs fresh
    from database.utils.migrated_database_utils import close_cached_service

    close_cached_service()

    with patch("mysql.connector.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [1]
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Because the canonical host/port mismatch is fatal, create_database_service should raise
        with pytest.raises(ChromaCanonicalValidationError):
            create_database_service()
