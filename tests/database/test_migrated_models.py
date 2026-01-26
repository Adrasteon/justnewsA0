"""
Tests for Migrated Database Models

Comprehensive tests for the migrated database models covering:
- Source model operations
- Article model operations
- ArticleSourceMap model operations
- MigratedDatabaseService operations
- Vector search and semantic operations
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from database.models.migrated_models import (
    Article,
    ArticleSourceMap,
    MigratedDatabaseService,
    Source,
)


class TestSourceModel:
    """Test Source model operations"""

    def test_source_init_default_values(self):
        """Test Source initialization with default values"""
        source = Source(
            id=1, url="https://example.com", domain="example.com", name="Example News"
        )

        assert source.id == 1
        assert source.url == "https://example.com"
        assert source.domain == "example.com"
        assert source.name == "Example News"
        assert source.paywall is False
        assert source.paywall_type is None
        assert source.metadata == {}
        assert source.created_at is None
        assert source.updated_at is None

    def test_source_init_with_all_values(self):
        """Test Source initialization with all values"""
        metadata = {"category": "news", "reliability": 0.9}
        created_at = datetime.now()

        source = Source(
            id=1,
            url="https://example.com",
            domain="example.com",
            name="Example News",
            description="A news source",
            country="US",
            language="en",
            paywall=True,
            paywall_type="soft",
            last_verified=created_at,
            metadata=metadata,
            created_at=created_at,
            updated_at=created_at,
        )

        assert source.id == 1
        assert source.description == "A news source"
        assert source.country == "US"
        assert source.language == "en"
        assert source.paywall is True
        assert source.paywall_type == "soft"
        assert source.last_verified == created_at
        assert source.metadata == metadata
        assert source.created_at == created_at
        assert source.updated_at == created_at

    def test_source_from_row(self):
        """Test creating Source from database row"""
        row = (
            1,  # id
            "https://example.com",  # url
            "example.com",  # domain
            "Example News",  # name
            "A news source",  # description
            "US",  # country
            "en",  # language
            True,  # paywall
            "hard",  # paywall_type
            datetime(2024, 1, 1),  # last_verified
            '{"category": "news"}',  # metadata
            datetime(2024, 1, 1),  # created_at
            datetime(2024, 1, 2),  # updated_at
        )

        source = Source.from_row(row)

        assert source.id == 1
        assert source.url == "https://example.com"
        assert source.domain == "example.com"
        assert source.name == "Example News"
        assert source.description == "A news source"
        assert source.country == "US"
        assert source.language == "en"
        assert source.paywall is True
        assert source.paywall_type == "hard"
        assert source.metadata == {"category": "news"}

    def test_source_from_row_with_null_metadata(self):
        """Test creating Source from row with null metadata"""
        row = (
            1,
            "https://example.com",
            "example.com",
            "Example News",
            None,
            None,
            None,
            False,
            None,
            None,
            None,
            None,
            None,
        )

        source = Source.from_row(row)

        assert source.metadata == {}

    def test_source_to_dict(self):
        """Test converting Source to dictionary"""
        metadata = {"category": "news"}
        created_at = datetime(2024, 1, 1)

        source = Source(
            id=1,
            url="https://example.com",
            domain="example.com",
            name="Example News",
            metadata=metadata,
            created_at=created_at,
        )

        result = source.to_dict()

        expected = {
            "id": 1,
            "url": "https://example.com",
            "domain": "example.com",
            "name": "Example News",
            "description": None,
            "country": None,
            "language": None,
            "paywall": False,
            "paywall_type": None,
            "last_verified": None,
            "metadata": metadata,
            "created_at": created_at,
            "updated_at": None,
        }

        assert result == expected


class TestArticleModel:
    """Test Article model operations"""

    def test_article_init_default_values(self):
        """Test Article initialization with default values"""
        article = Article(
            id=1,
            url="https://example.com/article1",
            title="Test Article",
            content="Article content",
        )

        assert article.id == 1
        assert article.url == "https://example.com/article1"
        assert article.title == "Test Article"
        assert article.content == "Article content"
        assert article.analyzed is False
        assert article.tags == []
        assert article.authors == []
        assert article.needs_review is False
        assert article.review_reasons == []
        assert article.extraction_metadata == {}
        assert article.structured_metadata == {}
        assert article.metadata == {}
        # New synthesis fields default to not-synthesized
        assert article.is_synthesized is False
        assert article.input_cluster_ids == []
        assert article.synth_model is None
        assert article.is_published is False

    def test_article_init_with_all_values(self):
        """Test Article initialization with all values"""
        tags = ["politics", "election"]
        authors = ["John Doe"]
        review_reasons = ["content_check"]
        extraction_metadata = {"confidence": 0.95}
        structured_metadata = {"word_count": 500}
        metadata = {"category": "news"}
        created_at = datetime.now()

        article = Article(
            id=1,
            url="https://example.com/article1",
            title="Test Article",
            content="Article content",
            summary="Article summary",
            analyzed=True,
            source_id=1,
            created_at=created_at,
            normalized_url="https://example.com/article1",
            url_hash="abc123",
            url_hash_algo="sha256",
            language="en",
            section="politics",
            tags=tags,
            authors=authors,
            raw_html_ref="html123",
            extraction_confidence=0.95,
            needs_review=True,
            review_reasons=review_reasons,
            extraction_metadata=extraction_metadata,
            structured_metadata=structured_metadata,
            publication_date=created_at,
            metadata=metadata,
            collection_timestamp=created_at,
        )

        assert article.summary == "Article summary"
        assert article.analyzed is True
        assert article.source_id == 1
        assert article.normalized_url == "https://example.com/article1"
        assert article.url_hash == "abc123"
        assert article.url_hash_algo == "sha256"
        assert article.language == "en"
        assert article.section == "politics"
        assert article.tags == tags
        assert article.authors == authors
        assert article.raw_html_ref == "html123"
        assert article.extraction_confidence == 0.95
        assert article.needs_review is True
        assert article.review_reasons == review_reasons
        assert article.extraction_metadata == extraction_metadata
        assert article.structured_metadata == structured_metadata
        assert article.publication_date == created_at
        assert article.metadata == metadata
        assert article.collection_timestamp == created_at

    def test_article_from_row(self):
        """Test creating Article from database row"""
        created_at = datetime(2024, 1, 1)
        row = (
            1,  # id
            "https://example.com/article1",  # url
            "Test Article",  # title
            "Article content",  # content
            "Article summary",  # summary
            True,  # analyzed
            1,  # source_id
            created_at,  # created_at
            created_at,  # updated_at
            "https://example.com/article1",  # normalized_url
            "abc123",  # url_hash
            "sha256",  # url_hash_algo
            "en",  # language
            "politics",  # section
            '["politics", "election"]',  # tags
            '["John Doe"]',  # authors
            "html123",  # raw_html_ref
            0.95,  # extraction_confidence
            True,  # needs_review
            '["content_check"]',  # review_reasons
            '{"confidence": 0.95}',  # extraction_metadata
            '{"word_count": 500}',  # structured_metadata
            created_at,  # publication_date
            '{"category": "news"}',  # metadata
            created_at,  # collection_timestamp
            False,  # is_synthesized
            "[]",  # input_cluster_ids
            None,  # synth_model
            None,  # synth_version
            None,  # synth_prompt_id
            None,  # synth_trace
            None,  # critic_result
            None,  # fact_check_status
            None,  # fact_check_trace
            False,  # is_published
            None,  # published_at
            None,  # created_by
        )

        article = Article.from_row(row)

        assert article.id == 1
        assert article.url == "https://example.com/article1"
        assert article.title == "Test Article"
        assert article.content == "Article content"
        assert article.summary == "Article summary"
        assert article.analyzed is True
        assert article.source_id == 1
        assert article.tags == ["politics", "election"]
        assert article.authors == ["John Doe"]
        assert article.needs_review is True
        assert article.review_reasons == ["content_check"]
        assert article.extraction_metadata == {"confidence": 0.95}
        assert article.structured_metadata == {"word_count": 500}
        assert article.metadata == {"category": "news"}
        # When reading from a row without synthesis columns, they default
        assert article.is_synthesized is False
        assert article.input_cluster_ids == []
        assert article.synth_model is None

    def test_article_from_row_with_nulls(self):
        """Test creating Article from row with null values"""
        row = (
            1,
            "https://example.com/article1",
            "Test Article",
            "Content",
            None,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            None,
            None,
            None,
            None,
            None,
            None,
        )

        article = Article.from_row(row)

        assert article.tags == []
        assert article.authors == []
        assert article.needs_review is False
        assert article.review_reasons == []
        assert article.extraction_metadata == {}
        assert article.structured_metadata == {}
        assert article.metadata == {}
        assert article.is_synthesized is False
        assert article.input_cluster_ids == []

    def test_article_to_dict(self):
        """Test converting Article to dictionary"""
        tags = ["politics"]
        metadata = {"category": "news"}
        created_at = datetime(2024, 1, 1)

        article = Article(
            id=1,
            url="https://example.com/article1",
            title="Test Article",
            content="Content",
            tags=tags,
            metadata=metadata,
            created_at=created_at,
        )

        result = article.to_dict()

        assert result["id"] == 1
        assert result["url"] == "https://example.com/article1"
        assert result["title"] == "Test Article"
        assert result["content"] == "Content"
        assert result["tags"] == tags
        assert result["metadata"] == metadata
        assert result["created_at"] == created_at


class TestArticleSourceMapModel:
    """Test ArticleSourceMap model operations"""

    def test_article_source_map_init(self):
        """Test ArticleSourceMap initialization"""
        detected_at = datetime.now()

        mapping = ArticleSourceMap(
            id=1,
            article_id=100,
            source_id=5,
            confidence=0.95,
            detected_at=detected_at,
            metadata={"method": "auto"},
        )

        assert mapping.id == 1
        assert mapping.article_id == 100
        assert mapping.source_id == 5
        assert mapping.confidence == 0.95
        assert mapping.detected_at == detected_at
        assert mapping.metadata == {"method": "auto"}

    def test_article_source_map_init_defaults(self):
        """Test ArticleSourceMap initialization with defaults"""
        mapping = ArticleSourceMap(article_id=100, source_id=5)

        assert mapping.confidence == 1.0
        assert mapping.metadata == {}

    def test_article_source_map_from_row(self):
        """Test creating ArticleSourceMap from database row"""
        detected_at = datetime(2024, 1, 1)
        row = (
            1,  # id
            100,  # article_id
            5,  # source_id
            0.95,  # confidence
            detected_at,  # detected_at
            '{"method": "auto"}',  # metadata
        )

        mapping = ArticleSourceMap.from_row(row)

        assert mapping.id == 1
        assert mapping.article_id == 100
        assert mapping.source_id == 5
        assert mapping.confidence == 0.95
        assert mapping.detected_at == detected_at
        assert mapping.metadata == {"method": "auto"}

    def test_article_source_map_from_row_null_metadata(self):
        """Test creating ArticleSourceMap from row with null metadata"""
        row = (1, 100, 5, 0.95, None, None)

        mapping = ArticleSourceMap.from_row(row)

        assert mapping.metadata == {}

    def test_article_source_map_to_dict(self):
        """Test converting ArticleSourceMap to dictionary"""
        detected_at = datetime(2024, 1, 1)
        metadata = {"method": "auto"}

        mapping = ArticleSourceMap(
            id=1,
            article_id=100,
            source_id=5,
            confidence=0.95,
            detected_at=detected_at,
            metadata=metadata,
        )

        result = mapping.to_dict()

        expected = {
            "id": 1,
            "article_id": 100,
            "source_id": 5,
            "confidence": 0.95,
            "detected_at": detected_at,
            "metadata": metadata,
        }

        assert result == expected


class TestMigratedDatabaseService:
    """Test MigratedDatabaseService operations"""

    @pytest.fixture
    def mock_config(self):
        """Mock database configuration"""
        return {
            "database": {
                "mariadb": {
                    "host": "localhost",
                    "port": 3306,
                    "user": "testuser",
                    "password": "testpass",
                    "database": "testdb",
                },
                "chromadb": {
                    "host": "localhost",
                    "port": 3307,
                    "collection": "articles",
                },
                "embedding": {"model": "all-MiniLM-L6-v2", "dimensions": 384},
            }
        }

    @pytest.fixture
    def mock_service(self, mock_config):
        """Create mock service for testing"""
        with patch("mysql.connector.connect") as mock_mb_connect:
            with patch("chromadb.HttpClient") as mock_chroma_client:
                with patch(
                    "sentence_transformers.SentenceTransformer"
                ) as mock_embedding:
                    # Setup mocks
                    mock_conn = MagicMock()
                    mock_mb_connect.return_value = mock_conn

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_client.get_collection.return_value = mock_collection
                    mock_chroma_client.return_value = mock_client

                    mock_model = MagicMock()
                    mock_embedding.return_value = mock_model

                    service = MigratedDatabaseService(mock_config)

                    # Store mocks for test access
                    service._mock_conn = mock_conn
                    service._mock_client = mock_client
                    service._mock_collection = mock_collection
                    service._mock_model = mock_model

                    yield service

    def test_service_init(self, mock_config, monkeypatch):
        """Test service initialization"""
        monkeypatch.setenv("CHROMADB_MODEL_SCOPED_COLLECTION", "1")
        with patch("mysql.connector.connect") as mock_mb_connect:
            with patch("chromadb.HttpClient") as mock_chroma_client:
                with patch(
                    "sentence_transformers.SentenceTransformer"
                ) as mock_embedding:
                    mock_conn = MagicMock()
                    mock_mb_connect.return_value = mock_conn

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_client.get_collection.return_value = mock_collection
                    mock_chroma_client.return_value = mock_client

                    mock_model = MagicMock()
                    mock_embedding.return_value = mock_model

                    service = MigratedDatabaseService(mock_config)

                    assert service.mb_conn == mock_conn
                    assert service.chroma_client == mock_client
                    assert service.collection == mock_collection
                    # embedding_model is loaded from get_shared_embedding_model, not mocked
                    assert service.embedding_model is not None

                    # Verify connections were made with correct params
                    mock_mb_connect.assert_called_once()
                    mock_chroma_client.assert_called_once_with(
                        host="localhost", port=3307
                    )
                    expected_collection = "articles__all-MiniLM-L6-v2__384"
                    mock_client.get_collection.assert_called_once_with(
                        expected_collection
                    )

    def test_collection_scoping_disabled(self, mock_config, monkeypatch):
        """When CHROMADB_MODEL_SCOPED_COLLECTION is false the base collection should be used."""
        monkeypatch.setenv("CHROMADB_MODEL_SCOPED_COLLECTION", "0")
        with patch("mysql.connector.connect") as mock_mb_connect:
            with patch("chromadb.HttpClient") as mock_chroma_client:
                with patch(
                    "sentence_transformers.SentenceTransformer"
                ) as mock_embedding:
                    mock_conn = MagicMock()
                    mock_mb_connect.return_value = mock_conn

                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_client.get_collection.return_value = mock_collection
                    mock_chroma_client.return_value = mock_client

                    mock_model = MagicMock()
                    mock_embedding.return_value = mock_model

                    service = MigratedDatabaseService(mock_config)

                    # scoping disabled -> should use base collection name
                    mock_client.get_collection.assert_called_once_with("articles")


    def test_close(self, mock_service):
        """Test closing database connections"""
        mock_service.close()

        mock_service.mb_conn.close.assert_called_once()

    def test_get_article_by_id_success(self, mock_service):
        """Test getting article by ID successfully"""
        mock_cursor = MagicMock()
        mock_row = (
            1,
            "https://example.com/article1",
            "Test Article",
            "Content",
            "Summary",
            True,
            1,
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
            "https://example.com/article1",
            "hash123",
            "sha256",
            "en",
            "politics",
            '["tag1"]',
            '["author1"]',
            "html123",
            0.95,
            False,
            "[]",
            "{}",
            "{}",
            datetime(2024, 1, 1),
            '{"meta": "data"}',
            datetime(2024, 1, 1),
        )
        mock_cursor.fetchone.return_value = mock_row
        mock_service.mb_conn.cursor.return_value = mock_cursor

        result = mock_service.get_article_by_id(1)

        assert result is not None
        assert isinstance(result, Article)
        assert result.id == 1
        assert result.title == "Test Article"

        mock_cursor.execute.assert_called_once()
        mock_cursor.close.assert_called_once()

    def test_get_article_by_id_not_found(self, mock_service):
        """Test getting article by ID when not found"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_service.mb_conn.cursor.return_value = mock_cursor

        result = mock_service.get_article_by_id(999)

        assert result is None

    def test_get_article_by_id_error(self, mock_service):
        """Test getting article by ID with database error"""
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("DB Error")
        mock_service.mb_conn.cursor.return_value = mock_cursor

        result = mock_service.get_article_by_id(1)

        assert result is None

    def test_get_source_by_id_success(self, mock_service):
        """Test getting source by ID successfully"""
        mock_cursor = MagicMock()
        mock_row = (
            1,
            "https://example.com",
            "example.com",
            "Example News",
            "Description",
            "US",
            "en",
            False,
            None,
            datetime(2024, 1, 1),
            '{"meta": "data"}',
            datetime(2024, 1, 1),
            datetime(2024, 1, 2),
        )
        mock_cursor.fetchone.return_value = mock_row
        mock_service.mb_conn.cursor.return_value = mock_cursor

        result = mock_service.get_source_by_id(1)

        assert result is not None
        assert isinstance(result, Source)
        assert result.id == 1
        assert result.name == "Example News"

    def test_semantic_search_success(self, mock_service):
        """Test semantic search successfully"""
        # Mock embedding - use MagicMock with return_value that has tolist()
        mock_embedding = MagicMock()
        mock_embedding.tolist.return_value = [0.1] * 384
        mock_encode = MagicMock(return_value=mock_embedding)
        mock_service.embedding_model = MagicMock()
        mock_service.embedding_model.encode = mock_encode

        # Mock ChromaDB results
        mock_results = {
            "ids": [["1", "2"]],
            "metadatas": [[{"score": 0.9}, {"score": 0.8}]],
            "documents": [["doc1"], ["doc2"]],
            "distances": [[0.1, 0.2]],
        }
        mock_service.collection.query.return_value = mock_results

        # Mock article lookup
        mock_article = Article(id=1, title="Test Article", content="Content")
        with patch.object(mock_service, "get_article_by_id", return_value=mock_article):
            with patch.object(mock_service, "get_source_by_id", return_value=None):
                results = mock_service.semantic_search("test query", n_results=2)

                assert len(results) == 2
                assert results[0]["article"]["id"] == 1
                assert results[0]["similarity_score"] == 0.9  # 1.0 - 0.1
                assert results[1]["similarity_score"] == 0.8  # 1.0 - 0.2

    def test_semantic_search_error(self, mock_service):
        """Test semantic search with error"""
        # Properly mock encode as a callable with side_effect
        mock_encode = MagicMock(side_effect=Exception("Embedding error"))
        mock_service.embedding_model = MagicMock()
        mock_service.embedding_model.encode = mock_encode

        results = mock_service.semantic_search("test query")

        assert len(results) == 0

    def test_search_articles_by_text(self, mock_service):
        """Test text search in articles"""
        mock_cursor = MagicMock()
        mock_results = [
            {"id": 1, "title": "Test Article", "source_name": "Test Source"}
        ]
        mock_cursor.fetchall.return_value = mock_results
        mock_service.mb_conn.cursor.return_value = mock_cursor

        results = mock_service.search_articles_by_text("test query", limit=5)

        assert results == mock_results
        mock_cursor.execute.assert_called_once()

    def test_get_recent_articles(self, mock_service):
        """Test getting recent articles"""
        mock_cursor = MagicMock()
        mock_results = [
            {"id": 1, "title": "Recent Article", "created_at": datetime(2024, 1, 1)}
        ]
        mock_cursor.fetchall.return_value = mock_results
        mock_service.mb_conn.cursor.return_value = mock_cursor

        results = mock_service.get_recent_articles(limit=10)

        assert results == mock_results

    def test_get_articles_by_source(self, mock_service):
        """Test getting articles by source"""
        mock_cursor = MagicMock()
        mock_results = [{"id": 1, "title": "Source Article", "source_id": 5}]
        mock_cursor.fetchall.return_value = mock_results
        mock_service.mb_conn.cursor.return_value = mock_cursor

        results = mock_service.get_articles_by_source(5, limit=10)

        assert results == mock_results
