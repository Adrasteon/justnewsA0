"""
Tests for JustNews Semantic Search Service
"""

from unittest.mock import Mock, patch

import pytest

from common.semantic_search_service import (
    SearchResponse,
    SearchResult,
    SemanticSearchService,
    async_search,
    get_search_service,
)


class TestSearchResult:
    """Test SearchResult dataclass"""

    def test_search_result_creation(self):
        """Test SearchResult creation with all fields"""
        result = SearchResult(
            article_id=1,
            title="Test Article",
            content="Test content",
            source_name="Test Source",
            published_date="2023-01-01",
            similarity_score=0.85,
            metadata={"key": "value"},
        )

        assert result.article_id == 1
        assert result.title == "Test Article"
        assert result.content == "Test content"
        assert result.source_name == "Test Source"
        assert result.published_date == "2023-01-01"
        assert result.similarity_score == 0.85
        assert result.metadata == {"key": "value"}


class TestSearchResponse:
    """Test SearchResponse dataclass"""

    def test_search_response_creation(self):
        """Test SearchResponse creation"""
        results = [
            SearchResult(1, "Title", "Content", "Source", "2023-01-01", 0.8, {}),
            SearchResult(2, "Title2", "Content2", "Source2", "2023-01-02", 0.7, {}),
        ]

        response = SearchResponse(
            query="test query",
            results=results,
            total_results=2,
            search_time=0.5,
            search_type="semantic",
        )

        assert response.query == "test query"
        assert len(response.results) == 2
        assert response.total_results == 2
        assert response.search_time == 0.5
        assert response.search_type == "semantic"


class TestSemanticSearchService:
    """Test SemanticSearchService class"""

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_initialization(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test service initialization"""
        mock_config = {"embedding": {"model": "test-model"}}
        mock_get_config.return_value = mock_config

        mock_service = Mock()
        mock_create_service.return_value = mock_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        service = SemanticSearchService(mock_config)

        assert service.config == mock_config
        assert service.db_service == mock_service
        mock_transformer.assert_called_once_with("test-model")
        assert service.embedding_model == mock_model

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_initialization_default_config(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test service initialization with default config"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_service = Mock()
        mock_create_service.return_value = mock_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        _service = SemanticSearchService()

        mock_get_config.assert_called_once()
        mock_transformer.assert_called_once_with("all-MiniLM-L6-v2")

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_semantic_search(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test semantic search functionality"""
        # Setup mocks
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_model.encode.return_value = [0.1, 0.2, 0.3]  # Mock embedding
        mock_transformer.return_value = mock_model

        # Mock ChromaDB query results
        mock_db_service.collection.query.return_value = {
            "ids": [["1", "2"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"key": "value1"}, {"key": "value2"}]],
            "distances": [[0.2, 0.3]],  # Distances that convert to similarities
        }

        # Mock article retrieval
        service = SemanticSearchService()
        service._get_article_by_id = Mock()
        service._get_article_by_id.side_effect = [
            {
                "id": 1,
                "title": "Article 1",
                "content": "Content 1",
                "source_name": "Source 1",
                "published_date": "2023-01-01",
            },
            {
                "id": 2,
                "title": "Article 2",
                "content": "Content 2",
                "source_name": "Source 2",
                "published_date": "2023-01-02",
            },
        ]

        # Perform search
        response = service.search("test query", n_results=2, search_type="semantic")

        assert response.query == "test query"
        assert response.search_type == "semantic"
        assert len(response.results) == 2
        assert response.total_results == 2
        assert response.search_time > 0

        # Check results
        assert response.results[0].article_id == 1
        assert response.results[0].title == "Article 1"
        assert response.results[0].similarity_score == 0.8  # 1.0 - 0.2

        assert response.results[1].article_id == 2
        assert response.results[1].title == "Article 2"
        assert response.results[1].similarity_score == 0.7  # 1.0 - 0.3

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_text_search(self, mock_transformer, mock_create_service, mock_get_config):
        """Test text-based search"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        # Mock text search results
        mock_db_service.search_articles_by_text.return_value = [
            {
                "id": 1,
                "title": "Article 1",
                "content": "Content 1",
                "source_name": "Source 1",
                "publication_date": "2023-01-01",
            }
        ]

        service = SemanticSearchService()
        response = service.search("test query", search_type="text")

        assert response.search_type == "text"
        assert len(response.results) == 1
        assert response.results[0].article_id == 1
        assert response.results[0].similarity_score == 1.0

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_hybrid_search(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test hybrid search combining semantic and text"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_model.encode.return_value = [0.1, 0.2, 0.3]
        mock_transformer.return_value = mock_model

        # Mock semantic search results
        mock_db_service.collection.query.return_value = {
            "ids": [["1"]],
            "documents": [["doc1"]],
            "metadatas": [[{}]],
            "distances": [[0.1]],
        }

        # Mock text search results
        mock_db_service.search_articles_by_text.return_value = [
            {
                "id": 2,
                "title": "Article 2",
                "content": "Content 2",
                "source_name": "Source 2",
                "publication_date": "2023-01-02",
            }
        ]

        service = SemanticSearchService()
        service._get_article_by_id = Mock()
        service._get_article_by_id.side_effect = [
            {
                "id": 1,
                "title": "Article 1",
                "content": "Content 1",
                "source_name": "Source 1",
                "published_date": "2023-01-01",
            },
            {
                "id": 2,
                "title": "Article 2",
                "content": "Content 2",
                "source_name": "Source 2",
                "published_date": "2023-01-02",
            },
        ]

        response = service.search("test query", search_type="hybrid")

        assert response.search_type == "hybrid"
        # Should have results from both semantic and text search
        assert len(response.results) >= 1

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_search_with_min_score_filtering(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test search with minimum score filtering"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_model.encode.return_value = [0.1, 0.2, 0.3]
        mock_transformer.return_value = mock_model

        # Mock results with low similarity scores
        mock_db_service.collection.query.return_value = {
            "ids": [["1", "2"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{}, {}]],
            "distances": [[0.8, 0.9]],  # Low similarities (0.2, 0.1)
        }

        service = SemanticSearchService()
        service._get_article_by_id = Mock(
            return_value={
                "id": 1,
                "title": "Article 1",
                "content": "Content 1",
                "source_name": "Source 1",
                "published_date": "2023-01-01",
            }
        )

        response = service.search("test query", min_score=0.5)

        # Should filter out low-scoring results
        assert len(response.results) == 0

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_search_error_handling(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test search error handling"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        # Mock search to raise exception
        mock_db_service.collection.query.side_effect = Exception("Search failed")

        service = SemanticSearchService()
        response = service.search("test query")

        assert response.query == "test query"
        assert len(response.results) == 0
        assert response.total_results == 0
        assert response.search_time > 0

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_invalid_search_type(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test invalid search type raises ValueError"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        service = SemanticSearchService()

        with pytest.raises(ValueError, match="Unsupported search type"):
            service.search("test query", search_type="invalid")

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_get_similar_articles(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test getting similar articles"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_model.encode.return_value = [0.1, 0.2, 0.3]
        mock_transformer.return_value = mock_model

        service = SemanticSearchService()

        # Mock article retrieval
        service._get_article_by_id = Mock(
            return_value={
                "id": 1,
                "title": "Reference Article",
                "content": "Reference content",
                "source_name": "Source",
                "published_date": "2023-01-01",
            }
        )

        # Mock semantic search results
        service._semantic_search = Mock(
            return_value=[
                SearchResult(
                    2, "Similar Article", "Content", "Source", "2023-01-02", 0.8, {}
                )
            ]
        )

        results = service.get_similar_articles(1, n_results=5)

        assert len(results) == 1
        assert results[0].article_id == 2
        service._semantic_search.assert_called_once()

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_get_similar_articles_not_found(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test getting similar articles when reference article not found"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        service = SemanticSearchService()
        service._get_article_by_id = Mock(return_value=None)

        results = service.get_similar_articles(999)

        assert results == []

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_get_articles_by_category(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test getting articles by category"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        service = SemanticSearchService()
        service._semantic_search = Mock(return_value=[])

        _results = service.get_articles_by_category("technology")

        service._semantic_search.assert_called_once_with("technology", 10, 0.0)

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_get_recent_articles_with_search(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test getting recent articles with search query"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        service = SemanticSearchService()
        service._hybrid_search = Mock(return_value=[])

        _results = service.get_recent_articles_with_search("test query")

        service._hybrid_search.assert_called_once_with("test query", 10, 0.0)

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_get_recent_articles_without_search(
        self, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test getting recent articles without search query"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        # Mock recent articles
        mock_db_service.get_recent_articles.return_value = [
            {
                "id": 1,
                "title": "Recent Article",
                "content": "Content",
                "source_name": "Source",
                "publication_date": "2023-01-01",
            }
        ]

        service = SemanticSearchService()
        results = service.get_recent_articles_with_search()

        assert len(results) == 1
        assert results[0].article_id == 1
        mock_db_service.get_recent_articles.assert_called_once_with(10)

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    @patch("common.semantic_search_service.get_database_stats")
    def test_get_search_statistics(
        self, mock_get_stats, mock_transformer, mock_create_service, mock_get_config
    ):
        """Test getting search statistics"""
        mock_config = {"embedding": {"model": "test-model", "dimensions": 384}}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        mock_get_stats.return_value = {"db_stats": "value"}

        service = SemanticSearchService()
        stats = service.get_search_statistics()

        assert stats["db_stats"] == "value"
        assert stats["embedding_model"] == "test-model"
        assert stats["embedding_dimensions"] == 384
        assert stats["cache_size"] == 0
        assert stats["cache_max_size"] == 1000

    @patch("common.semantic_search_service.get_db_config")
    @patch("common.semantic_search_service.create_database_service")
    @patch("common.semantic_search_service.SentenceTransformer")
    def test_clear_cache(self, mock_transformer, mock_create_service, mock_get_config):
        """Test clearing the article cache"""
        mock_config = {}
        mock_get_config.return_value = mock_config

        mock_db_service = Mock()
        mock_create_service.return_value = mock_db_service

        mock_model = Mock()
        mock_transformer.return_value = mock_model

        service = SemanticSearchService()
        service._article_cache = {"key": "value"}

        service.clear_cache()

        assert len(service._article_cache) == 0


class TestGlobalFunctions:
    """Test global service functions"""

    @patch("common.semantic_search_service.SemanticSearchService")
    def test_get_search_service_singleton(self, mock_service_class):
        """Test get_search_service returns singleton instance"""
        mock_instance = Mock()
        mock_service_class.return_value = mock_instance

        # Reset global instance
        import common.semantic_search_service

        common.semantic_search_service._search_service_instance = None

        service1 = get_search_service()
        service2 = get_search_service()

        assert service1 is service2
        assert service1 is mock_instance
        mock_service_class.assert_called_once()

    @pytest.mark.asyncio
    @patch("common.semantic_search_service.get_search_service")
    async def test_async_search(self, mock_get_service):
        """Test async search function"""
        mock_service = Mock()
        mock_response = SearchResponse(
            query="test",
            results=[],
            total_results=0,
            search_time=0.1,
            search_type="semantic",
        )
        mock_service.search.return_value = mock_response
        mock_get_service.return_value = mock_service

        response = await async_search("test query")

        assert response == mock_response
        mock_service.search.assert_called_once_with("test query", 10, "semantic", 0.0)
