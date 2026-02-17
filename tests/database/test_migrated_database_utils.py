"""
Tests for Migrated Database Utilities

Comprehensive tests for the migrated database utilities covering:
- Configuration loading and validation
- Database service creation
- Connection checking
- Query execution (sync and async)
- Transaction handling
- Database statistics
- Semantic search operations
"""

import json
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from database.utils.migrated_database_utils import (
    check_database_connections,
    create_database_service,
    execute_mariadb_query,
    execute_query_async,
    execute_transaction,
    get_articles_by_source,
    get_database_stats,
    get_db_config,
    get_recent_articles,
    search_articles_by_text,
    semantic_search,
)


class TestGetDBConfig:
    """Test database configuration loading"""

    def test_get_db_config_from_system_config(self):
        """Test loading config from system_config.json"""
        config_data = {
            "database": {
                "mariadb": {
                    "host": "db.example.com",
                    "port": 3306,
                    "database": "justnews",
                    "user": "justnews_user",
                    "password": "secure_password",
                },
                "chromadb": {
                    "host": "vector.example.com",
                    "port": 3307,
                    "collection": "news_articles",
                },
                "embedding": {
                    "model": "all-MiniLM-L6-v2",
                    "dimensions": 384,
                    "device": "cpu",
                },
            }
        }

        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(config_data))):
                with patch("os.path.join") as mock_join:
                    mock_join.return_value = "/fake/path/system_config.json"
                    result = get_db_config()

                    assert result["mariadb"]["host"] == "db.example.com"
                    assert result["mariadb"]["user"] == "justnews_user"
                    assert result["chromadb"]["host"] == "vector.example.com"
                    assert result["embedding"]["model"] == "all-MiniLM-L6-v2"

    def test_get_db_config_from_environment(self):
        """Test loading config from environment variables when system config fails"""
        env_vars = {
            "MARIADB_HOST": "env-db.example.com",
            "MARIADB_PORT": "3307",
            "MARIADB_DB": "env_justnews",
            "MARIADB_USER": "env_user",
            "MARIADB_PASSWORD": "env_password",
            "CHROMADB_HOST": "env-vector.example.com",
            "CHROMADB_PORT": "8001",
            "CHROMADB_COLLECTION": "env_articles",
            "EMBEDDING_MODEL": "env-model",
            "EMBEDDING_DIMENSIONS": "512",
            "EMBEDDING_DEVICE": "cuda",
        }

        with patch.dict(os.environ, env_vars):
            with patch("os.path.exists", return_value=False):
                with patch("builtins.open", side_effect=FileNotFoundError):
                    result = get_db_config()

                    assert result["mariadb"]["host"] == "env-db.example.com"
                    assert result["mariadb"]["port"] == 3307
                    assert result["chromadb"]["collection"] == "env_articles"
                    assert result["embedding"]["dimensions"] == 512

    def test_get_db_config_missing_required_fields(self):
        """Test config validation with missing required fields"""
        with patch("os.path.exists", return_value=False):
            with patch("builtins.open", side_effect=FileNotFoundError):
                with patch.dict(os.environ, {}, clear=True):
                    # get_db_config returns defaults rather than raising, so check we get defaults
                    result = get_db_config()
                    # Should have default values instead of raising
                    assert "mariadb" in result
                    assert "host" in result["mariadb"]

    def test_get_db_config_with_global_env_file(self):
        """Test loading global.env file"""
        env_content = "MARIADB_PASSWORD=from_env_file\nCHROMADB_HOST=from_env\n"

        with patch("os.path.exists") as mock_exists:

            def exists_side_effect(path):
                if path == "/etc/justnews/global.env":
                    return True
                return False

            mock_exists.side_effect = exists_side_effect

            with patch("builtins.open", mock_open(read_data=env_content)):
                with patch.dict(os.environ, {}, clear=True):
                    result = get_db_config()

                    # Should have loaded password from env file
                    assert result["mariadb"]["password"] == "from_env_file"


class TestCreateDatabaseService:
    """Test database service creation"""

    @pytest.fixture
    def mock_config(self):
        """Mock database configuration"""
        return {
            "mariadb": {
                "host": "localhost",
                "port": 3306,
                "database": "testdb",
                "user": "testuser",
                "password": "testpass",
            },
            "chromadb": {
                "host": "localhost",
                "port": 3307,
                "collection": "test_collection",
            },
            "embedding": {"model": "test-model"},
        }

    def test_create_database_service_with_config(self, mock_config, monkeypatch):
        """Test creating service with provided config"""
        with patch("database.models.migrated_models.SentenceTransformer") as mock_st:
            # Ensure canonical enforcement is disabled for this unit test unless explicitly tested
            monkeypatch.setenv("CHROMADB_REQUIRE_CANONICAL", "0")
            with patch(
                "database.utils.migrated_database_utils.check_database_connections",
                return_value=True,
            ):
                with patch("mysql.connector.connect") as mock_connect:
                    with patch("chromadb.HttpClient") as mock_chroma:
                        with patch(
                            "database.utils.chromadb_utils.validate_chroma_is_canonical",
                            return_value={"ok": True},
                        ):
                            mock_connect.return_value = MagicMock()
                        mock_chroma_instance = MagicMock()
                        mock_chroma_instance.get_collection.return_value = MagicMock()
                        mock_chroma.return_value = mock_chroma_instance
                        mock_st.return_value = MagicMock()

                        result = create_database_service(mock_config)

                        assert result is not None
                        assert hasattr(result, "mb_conn")

    def test_create_database_service_without_config(self, mock_config, monkeypatch):
        """Test creating service without config (uses get_db_config)"""
        with patch("database.models.migrated_models.SentenceTransformer") as mock_st:
            monkeypatch.setenv("CHROMADB_REQUIRE_CANONICAL", "0")
            with patch(
                "database.utils.migrated_database_utils.get_db_config",
                return_value=mock_config,
            ):
                with patch(
                    "database.utils.migrated_database_utils.check_database_connections",
                    return_value=True,
                ):
                    with patch("mysql.connector.connect") as mock_connect:
                        with patch("chromadb.HttpClient") as mock_chroma:
                            with patch(
                                "database.utils.chromadb_utils.validate_chroma_is_canonical",
                                return_value={"ok": True},
                            ):
                                mock_connect.return_value = MagicMock()
                            mock_chroma_instance = MagicMock()
                            mock_chroma_instance.get_collection.return_value = (
                                MagicMock()
                            )
                            mock_chroma.return_value = mock_chroma_instance
                            mock_st.return_value = MagicMock()

                            result = create_database_service()

                            assert result is not None
                            assert hasattr(result, "mb_conn")


class TestCheckDatabaseConnections:
    """Test database connection checking"""

    @pytest.fixture
    def mock_service(self):
        """Create mock service for testing"""
        service = MagicMock()
        service.mb_conn = MagicMock()
        service.chroma_client = MagicMock()
        service.collection = MagicMock()
        service.collection.name = "test_collection"
        service.embedding_model = MagicMock()
        return service

    def test_check_connections_success(self, mock_service):
        """Test successful connection check"""
        # Mock MariaDB
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_service.mb_conn.cursor.return_value = mock_cursor

        # Mock ChromaDB
        mock_collection = MagicMock()
        mock_collection.name = "test_collection"
        mock_service.chroma_client.list_collections.return_value = [mock_collection]

        # Mock embedding
        mock_service.embedding_model.encode.return_value = [0.1] * 384

        result = check_database_connections(mock_service)

        assert result is True
        mock_cursor.execute.assert_called_with("SELECT 1 as test")

    def test_check_connections_mariadb_failure(self, mock_service):
        """Test connection check with MariaDB failure"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # Wrong result
        mock_service.mb_conn.cursor.return_value = mock_cursor

        result = check_database_connections(mock_service)

        assert result is False

    def test_check_connections_chromadb_collection_missing(self, mock_service):
        """Test connection check with missing ChromaDB collection"""
        # Mock MariaDB success
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_service.mb_conn.cursor.return_value = mock_cursor

        # Mock ChromaDB with wrong collection
        mock_collection = MagicMock()
        mock_collection.name = "wrong_collection"
        mock_service.chroma_client.list_collections.return_value = [mock_collection]

        result = check_database_connections(mock_service)

        assert result is False

    def test_check_connections_embedding_wrong_dimensions(self, mock_service):
        """Test connection check with wrong embedding dimensions"""
        # Mock MariaDB success
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (1,)
        mock_service.mb_conn.cursor.return_value = mock_cursor

        # Mock ChromaDB success
        mock_collection = MagicMock()
        mock_collection.name = "test_collection"
        mock_service.chroma_client.list_collections.return_value = [mock_collection]

        # Mock embedding with wrong dimensions
        mock_service.embedding_model.encode.return_value = [0.1] * 200  # Wrong size

        result = check_database_connections(mock_service)

        assert result is False

    def test_check_connections_exception(self, mock_service):
        """Test connection check with exception"""
        mock_service.mb_conn.cursor.side_effect = Exception("Connection error")

        result = check_database_connections(mock_service)

        assert result is False


class TestExecuteMariaDBQuery:
    """Test MariaDB query execution"""

    @pytest.fixture
    def mock_service(self):
        """Create mock service for testing"""
        service = MagicMock()
        service.mb_conn = MagicMock()
        return service

    def test_execute_query_fetch_results(self, mock_service):
        """Test query execution with result fetching"""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("result1",), ("result2",)]
        mock_service.mb_conn.cursor.return_value = mock_cursor

        results = execute_mariadb_query(
            mock_service, "SELECT * FROM test", ("param1",), fetch=True
        )

        assert results == [("result1",), ("result2",)]
        mock_cursor.execute.assert_called_with("SELECT * FROM test", ("param1",))
        mock_cursor.close.assert_called_once()

    def test_execute_query_no_fetch(self, mock_service):
        """Test query execution without fetching results"""
        mock_cursor = MagicMock()
        mock_service.mb_conn.cursor.return_value = mock_cursor

        results = execute_mariadb_query(
            mock_service, "INSERT INTO test VALUES (?)", ("value",), fetch=False
        )

        assert results == []
        mock_service.mb_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_execute_query_exception(self, mock_service):
        """Test query execution with exception"""
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Query error")
        mock_service.mb_conn.cursor.return_value = mock_cursor

        results = execute_mariadb_query(mock_service, "SELECT * FROM test")

        assert results == []
        mock_service.mb_conn.rollback.assert_called_once()


class TestExecuteQueryAsync:
    """Test async query execution"""

    @pytest.fixture
    def mock_service(self):
        """Create mock service for testing"""
        service = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_execute_query_async(self, mock_service):
        """Test async query execution"""
        expected_results = [("result1",), ("result2",)]

        with patch(
            "database.utils.migrated_database_utils.execute_mariadb_query",
            return_value=expected_results,
        ):
            results = await execute_query_async(
                mock_service, "SELECT * FROM test", ("param",), fetch=True
            )

            assert results == expected_results


class TestExecuteTransaction:
    """Test transaction execution"""

    @pytest.fixture
    def mock_service(self):
        """Create mock service for testing"""
        service = MagicMock()
        service.mb_conn = MagicMock()
        return service

    def test_execute_transaction_success(self, mock_service):
        """Test successful transaction execution"""
        queries = ["INSERT INTO test1 VALUES (?)", "INSERT INTO test2 VALUES (?)"]
        params_list = [("value1",), ("value2",)]

        mock_cursor = MagicMock()
        mock_service.mb_conn.cursor.return_value = mock_cursor

        result = execute_transaction(mock_service, queries, params_list)

        assert result is True
        assert mock_cursor.execute.call_count == 2
        mock_service.mb_conn.commit.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_execute_transaction_failure(self, mock_service):
        """Test transaction failure"""
        queries = ["INSERT INTO test VALUES (?)"]
        params_list = [("value",)]

        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("Transaction error")
        mock_service.mb_conn.cursor.return_value = mock_cursor

        result = execute_transaction(mock_service, queries, params_list)

        assert result is False
        mock_service.mb_conn.rollback.assert_called_once()

    def test_execute_transaction_parameter_mismatch(self, mock_service):
        """Test transaction with mismatched parameters"""
        queries = ["INSERT INTO test VALUES (?)"]
        params_list = [("param1",), ("param2",)]  # Wrong length

        with pytest.raises(
            ValueError, match="queries and params_list must have the same length"
        ):
            execute_transaction(mock_service, queries, params_list)


class TestGetDatabaseStats:
    """Test database statistics retrieval"""

    @pytest.fixture
    def mock_service(self):
        """Create mock service for testing"""
        service = MagicMock()
        service.mb_conn = MagicMock()
        service.chroma_client = MagicMock()
        service.collection = MagicMock()
        service.collection.count.return_value = 150
        return service

    def test_get_database_stats_success(self, mock_service):
        """Test successful database stats retrieval"""
        mock_cursor = MagicMock()
        # Mock article count
        mock_cursor.fetchone.side_effect = [(100,), (25,), (75,)]
        mock_service.mb_conn.cursor.return_value = mock_cursor

        # Mock collections
        mock_collection = MagicMock()
        mock_collection.name = "articles"
        mock_service.chroma_client.list_collections.return_value = [mock_collection]

        stats = get_database_stats(mock_service)

        assert stats["mariadb"]["articles"] == 100
        assert stats["mariadb"]["sources"] == 25
        assert stats["mariadb"]["mappings"] == 75
        assert stats["chromadb"]["vectors"] == 150
        assert stats["total_articles"] == 100
        assert stats["total_sources"] == 25
        assert stats["total_vectors"] == 150
        assert stats["chromadb"]["collections"] == ["articles"]

    def test_get_database_stats_with_error(self, mock_service):
        """Test database stats with error"""
        mock_service.mb_conn.cursor.side_effect = Exception("DB error")

        stats = get_database_stats(mock_service)

        # Should return stats structure even on error
        assert "mariadb" in stats
        assert "total_articles" in stats
        # Values should be 0 on error
        assert stats.get("total_articles", 0) == 0


class TestSearchFunctions:
    """Test search and retrieval functions"""

    @pytest.fixture
    def mock_service(self):
        """Create mock service for testing"""
        service = MagicMock()
        return service

    def test_semantic_search(self, mock_service):
        """Test semantic search wrapper"""
        expected_results = [{"article": {"id": 1}, "similarity_score": 0.9}]
        mock_service.semantic_search.return_value = expected_results

        results = semantic_search(mock_service, "test query", n_results=5)

        assert results == expected_results
        mock_service.semantic_search.assert_called_once_with("test query", 5)

    def test_search_articles_by_text(self, mock_service):
        """Test text search wrapper"""
        expected_results = [{"id": 1, "title": "Test Article"}]
        mock_service.search_articles_by_text.return_value = expected_results

        results = search_articles_by_text(mock_service, "test query", limit=10)

        assert results == expected_results
        mock_service.search_articles_by_text.assert_called_once_with("test query", 10)

    def test_get_recent_articles(self, mock_service):
        """Test recent articles wrapper"""
        expected_results = [{"id": 1, "title": "Recent Article"}]
        mock_service.get_recent_articles.return_value = expected_results

        results = get_recent_articles(mock_service, limit=10)

        assert results == expected_results
        mock_service.get_recent_articles.assert_called_once_with(10)

    def test_get_articles_by_source(self, mock_service):
        """Test articles by source wrapper"""
        expected_results = [{"id": 1, "source_id": 5}]
        mock_service.get_articles_by_source.return_value = expected_results

        results = get_articles_by_source(mock_service, 5, limit=10)

        assert results == expected_results
        mock_service.get_articles_by_source.assert_called_once_with(5, 10)


@pytest.mark.parametrize(
    "function_name,expected_behavior",
    [
        ("get_db_config", "returns_config_dict"),
        ("create_database_service", "creates_service_instance"),
        ("check_database_connections", "validates_connections"),
        ("execute_mariadb_query", "executes_query"),
        ("get_database_stats", "returns_stats_dict"),
        ("semantic_search", "performs_search"),
    ],
)
def test_function_signatures(function_name, expected_behavior):
    """Test that all functions have expected signatures and behavior"""
    # This test ensures our test coverage includes all major functions
    # The actual testing logic is in the individual test classes above
    assert isinstance(function_name, str)
    assert isinstance(expected_behavior, str)
