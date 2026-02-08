"""
Test Configuration for Dual Database Tests

Provides fixtures, markers, and configuration for comprehensive
dual database testing (MariaDB + ChromaDB).
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from database.models.migrated_models import Article, MigratedDatabaseService, Source

# Test Markers
pytestmark = [pytest.mark.database, pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_config() -> dict[str, Any]:
    """Base test configuration for dual database setup"""
    return {
        "database": {
            "mariadb": {
                "host": "localhost",
                "port": 3306,
                "database": "justnews_test",
                "user": "test_user",
                "password": "test_password",
                "charset": "utf8mb4",
                "autocommit": False,
            },
            "chromadb": {
                "host": "localhost",
                "port": 3307,
                "collection": "test_articles",
                "settings": {"anonymized_telemetry": False},
            },
            "embedding": {
                "model": "all-MiniLM-L6-v2",
                "dimensions": 384,
                "device": "cpu",
                "cache_folder": "/tmp/test_cache",
            },
        },
        "testing": {
            "mock_connections": True,
            "use_real_embeddings": False,
            "cleanup_after_tests": True,
        },
    }


@pytest.fixture
def mock_mariadb_connection():
    """Mock MariaDB connection with cursor"""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.close = MagicMock()
    mock_conn.commit = MagicMock()
    mock_conn.rollback = MagicMock()
    return mock_conn, mock_cursor


@pytest.fixture
def mock_chromadb_client():
    """Mock ChromaDB client with collection"""
    mock_client = MagicMock()
    mock_collection = MagicMock()

    # Setup collection properties
    mock_collection.name = "test_articles"
    mock_collection.count.return_value = 0
    mock_collection.metadata = {"test": True}

    # Setup client methods
    mock_client.get_collection.return_value = mock_collection
    mock_client.list_collections.return_value = [mock_collection]
    mock_client.create_collection.return_value = mock_collection
    mock_client.delete_collection = MagicMock()

    return mock_client, mock_collection


@pytest.fixture
def mock_embedding_model():
    """Mock sentence transformer model"""
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.1] * 384  # Standard embedding dimensions
    mock_model.get_sentence_embedding_dimension.return_value = 384
    return mock_model


@pytest.fixture
def mock_database_service(
    test_config,
    mock_mariadb_connection,
    mock_chromadb_client,
    mock_embedding_model,
    monkeypatch,
):
    """Create a fully mocked database service"""
    mock_conn, mock_cursor = mock_mariadb_connection
    mock_client, mock_collection = mock_chromadb_client

    with patch("mysql.connector.connect", return_value=mock_conn):
        with patch("chromadb.HttpClient", return_value=mock_client):
            with patch(
                "sentence_transformers.SentenceTransformer",
                return_value=mock_embedding_model,
            ):
                # Disable canonical Chroma enforcement for most unit tests in this suite.
                monkeypatch.setenv("CHROMADB_REQUIRE_CANONICAL", "0")
                service = MigratedDatabaseService(test_config)

                # Store mocks for test access
                service._mock_conn = mock_conn
                service._mock_cursor = mock_cursor
                service._mock_client = mock_client
                service._mock_collection = mock_collection
                service._mock_model = mock_embedding_model

                yield service


@pytest.fixture
def sample_source_data():
    """Sample source data for testing"""
    return {
        "id": 1,
        "url": "https://example.com",
        "domain": "example.com",
        "name": "Example News",
        "created_at": datetime(2024, 1, 1, 12, 0, 0),
        "metadata": {"test": True, "version": "1.0"},
    }


@pytest.fixture
def sample_article_data():
    """Sample article data for testing"""
    return {
        "id": 1,
        "url": "https://example.com/article1",
        "title": "Test Article Title",
        "content": "This is a comprehensive test article content with enough text to be meaningful for testing purposes. It includes various topics and should work well with embedding models.",
        "summary": "A test article for database integration testing.",
        "is_active": True,
        "source_id": 1,
        "published_at": datetime(2024, 1, 1, 12, 0, 0),
        "updated_at": datetime(2024, 1, 2, 12, 0, 0),
        "canonical_url": "https://example.com/article1",
        "url_hash": "hash123456789",
        "content_hash": "content_hash_abc",
        "content_hash_algorithm": "sha256",
        "language": "en",
        "category": "technology",
        "tags": ["test", "integration", "database"],
        "authors": ["Test Author"],
        "raw_html": "<html><body>Test content</body></html>",
        "extraction_confidence": 0.95,
        "is_paywalled": False,
        "image_urls": ["https://example.com/image1.jpg"],
        "sentiment_analysis": {"polarity": 0.1, "subjectivity": 0.3},
        "word_count": 42,
        "read_time_minutes": 2,
        # created_at/updated_at already provided earlier in this record
    }


@pytest.fixture
def sample_source(sample_source_data):
    """Create a sample Source object"""
    return Source(**sample_source_data)


@pytest.fixture
def sample_article(sample_article_data):
    """Create a sample Article object"""
    return Article(**sample_article_data)


@pytest.fixture
def mock_query_results():
    """Mock database query results"""
    return {
        "articles": [
            {
                "id": 1,
                "title": "Test Article 1",
                "content": "Content 1",
                "source_id": 1,
                "created_at": datetime(2024, 1, 1),
            },
            {
                "id": 2,
                "title": "Test Article 2",
                "content": "Content 2",
                "source_id": 1,
                "created_at": datetime(2024, 1, 2),
            },
        ],
        "sources": [
            {
                "id": 1,
                "url": "https://example.com",
                "domain": "example.com",
                "name": "Example News",
                "created_at": datetime(2024, 1, 1),
            }
        ],
        "vectors": [
            {
                "id": "1",
                "metadata": {"article_id": 1, "score": 0.9},
                "document": "Test content 1",
            },
            {
                "id": "2",
                "metadata": {"article_id": 2, "score": 0.8},
                "document": "Test content 2",
            },
        ],
    }


@pytest.fixture
def mock_chromadb_results():
    """Mock ChromaDB query results"""
    return {
        "ids": [["1", "2"]],
        "metadatas": [
            [{"article_id": 1, "score": 0.9}],
            [{"article_id": 2, "score": 0.8}],
        ],
        "documents": [["Test content 1"], ["Test content 2"]],
        "distances": [[0.1, 0.2]],
    }


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment before each test"""
    # Any global test setup can go here
    yield
    # Cleanup after each test can go here


@pytest.fixture(autouse=True)
def _disable_chroma_canonical_in_tests(monkeypatch):
    """Disable CHROMADB_REQUIRE_CANONICAL during database tests by default.

    Tests that want canonical enforcement can override it using monkeypatch.setenv in the test body.
    """
    monkeypatch.setenv("CHROMADB_REQUIRE_CANONICAL", "0")
    yield


@pytest.fixture(scope="session", autouse=True)
def setup_test_session():
    """Setup test session"""
    # Any session-wide setup can go here
    yield
    # Cleanup after session can go here


# Custom test utilities
def assert_database_service_initialized(service: MigratedDatabaseService):
    """Assert that database service is properly initialized"""
    assert service.mb_conn is not None
    assert service.chroma_client is not None
    assert service.collection is not None
    assert service.embedding_model is not None
    assert service.config is not None


def assert_article_data_integrity(article: Article, expected_data: dict[str, Any]):
    """Assert article data integrity"""
    article_dict = article.to_dict()
    for key, expected_value in expected_data.items():
        if key in article_dict:
            if isinstance(expected_value, datetime):
                assert article_dict[key] == expected_value.isoformat()
            else:
                assert article_dict[key] == expected_value


def assert_source_data_integrity(source: Source, expected_data: dict[str, Any]):
    """Assert source data integrity"""
    source_dict = source.to_dict()
    for key, expected_value in expected_data.items():
        if key in source_dict:
            if isinstance(expected_value, datetime):
                assert source_dict[key] == expected_value.isoformat()
            else:
                assert source_dict[key] == expected_value


def mock_successful_transaction(cursor: MagicMock):
    """Setup cursor to simulate successful transaction"""
    cursor.execute.return_value = None
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None


def mock_failed_transaction(
    cursor: MagicMock, error_message: str = "Transaction failed"
):
    """Setup cursor to simulate failed transaction"""
    cursor.execute.side_effect = Exception(error_message)


# Async test utilities
async def async_assert_eventually_true(
    condition_func, timeout: float = 5.0, interval: float = 0.1
):
    """Assert that a condition becomes true within a timeout"""
    import time

    start_time = time.time()

    while time.time() - start_time < timeout:
        if condition_func():
            return
        await asyncio.sleep(interval)

    raise AssertionError(f"Condition did not become true within {timeout} seconds")


def parametrize_database_configs():
    """Parametrize different database configurations for testing"""
    configs = [
        # Standard configuration
        {
            "name": "standard",
            "config": {
                "database": {
                    "mariadb": {"host": "localhost", "port": 3306},
                    "chromadb": {"host": "localhost", "port": 3307},
                    "embedding": {"model": "all-MiniLM-L6-v2"},
                }
            },
        },
        # High availability configuration
        {
            "name": "high_availability",
            "config": {
                "database": {
                    "mariadb": {"host": "db-cluster", "port": 3306, "pool_size": 10},
                    "chromadb": {"host": "chroma-cluster", "port": 3307},
                    "embedding": {"model": "all-mpnet-base-v2", "device": "cuda"},
                }
            },
        },
        # Minimal configuration
        {
            "name": "minimal",
            "config": {
                "database": {
                    "mariadb": {"host": "localhost", "port": 3306},
                    "chromadb": {"host": "localhost", "port": 3307},
                    "embedding": {"model": "paraphrase-MiniLM-L3-v2"},
                }
            },
        },
    ]

    return pytest.mark.parametrize(
        "config_variant", configs, ids=[c["name"] for c in configs]
    )


# Performance testing utilities
def time_operation(operation_func, *args, **kwargs):
    """Time an operation and return result with timing"""
    import time

    start_time = time.time()
    result = operation_func(*args, **kwargs)
    end_time = time.time()

    return result, end_time - start_time


async def time_async_operation(operation_func, *args, **kwargs):
    """Time an async operation and return result with timing"""
    import time

    start_time = time.time()
    result = await operation_func(*args, **kwargs)
    end_time = time.time()

    return result, end_time - start_time


# Test data generators
def generate_test_articles(count: int, source_id: int = 1) -> list[Article]:
    """Generate test articles for bulk operations"""
    articles = []
    for i in range(count):
        article = Article(
            id=i + 1,
            url=f"https://example.com/article{i + 1}",
            title=f"Test Article {i + 1}",
            content=f"This is test content for article {i + 1}. " * 10,
            source_id=source_id,
            created_at=datetime(2024, 1, 1),
        )
        articles.append(article)
    return articles


def generate_test_sources(count: int) -> list[Source]:
    """Generate test sources for bulk operations"""
    sources = []
    for i in range(count):
        source = Source(
            id=i + 1,
            url=f"https://source{i + 1}.com",
            domain=f"source{i + 1}.com",
            name=f"Test Source {i + 1}",
            created_at=datetime(2024, 1, 1),
        )
        sources.append(source)
    return sources
