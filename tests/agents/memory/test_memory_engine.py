from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from agents.memory.memory_engine import MemoryEngine


@pytest.fixture
def mock_db_service():
    """Mock database service for testing."""
    mock_db = MagicMock()
    mock_db.mb_conn = MagicMock()
    mock_db.mb_conn.cursor.return_value = MagicMock()
    return mock_db


@pytest.fixture
def mock_embedding_model():
    """Mock embedding model for testing."""
    mock_model = MagicMock()
    return mock_model


@pytest_asyncio.fixture
async def memory_engine(mock_db_service, mock_embedding_model):
    """Create MemoryEngine instance with mocked dependencies."""
    with (
        patch(
            "database.utils.migrated_database_utils.create_database_service",
            return_value=mock_db_service,
        ),
        patch(
            "agents.memory.tools.get_embedding_model", return_value=mock_embedding_model
        ),
    ):
        engine = MemoryEngine()
        # Manually set the attributes since we're mocking the initialization
        engine.db_service = mock_db_service
        engine.embedding_model = mock_embedding_model
        engine.db_initialized = True
        yield engine


class TestMemoryEngineInitialization:
    """Test MemoryEngine initialization."""

    @pytest.mark.asyncio
    async def test_initialization_success(self, mock_db_service, mock_embedding_model):
        """Test successful initialization."""
        with (
            patch(
                "agents.memory.memory_engine.create_database_service",
                return_value=mock_db_service,
            ),
            patch(
                "agents.memory.memory_engine.get_embedding_model",
                return_value=mock_embedding_model,
            ),
        ):
            engine = MemoryEngine()
            await engine.initialize()
            # MemoryEngine.initialize() doesn't return anything (None), just sets db_initialized
            assert engine.db_initialized is True
            assert engine.db_service is not None
            assert engine.embedding_model is not None


class TestMemoryEngineArticleOperations:
    """Test MemoryEngine article operations."""

    @pytest.mark.asyncio
    async def test_save_article_success(
        self, memory_engine, mock_db_service, mock_embedding_model
    ):
        """Test successful article saving."""
        content = "Test article content"
        metadata = {
            "title": "Test Article",
            "url": "http://example.com",
            "source": "test_source",
        }

        with patch("agents.memory.memory_engine.save_article") as mock_save:
            mock_save.return_value = {"status": "saved", "article_id": 1}

            result = memory_engine.save_article(content, metadata)
            assert result == {"status": "saved", "article_id": 1}
            mock_save.assert_called_once_with(
                content,
                metadata,
                embedding_model=memory_engine.embedding_model,
                db_service=memory_engine.db_service,
            )

    @pytest.mark.asyncio
    async def test_save_article_failure(self, memory_engine):
        """Test article saving failure."""
        content = "Test article content"
        metadata = {
            "title": "Test Article",
            "url": "http://example.com",
            "source": "test_source",
        }

        with patch("agents.memory.memory_engine.save_article") as mock_save:
            mock_save.side_effect = Exception("Save failed")

            result = memory_engine.save_article(content, metadata)
            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_article_success(self, memory_engine, mock_db_service):
        """Test successful article retrieval."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "id": 1,
            "content": "Test content",
            "metadata": '{"title": "Test"}',
        }
        mock_db_service.mb_conn.cursor.return_value = mock_cursor

        result = memory_engine.get_article(1)
        assert result["id"] == 1
        assert result["content"] == "Test content"
        assert result["metadata"] == {"title": "Test"}

    @pytest.mark.asyncio
    async def test_get_article_not_found(self, memory_engine, mock_db_service):
        """Test article retrieval when not found."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_service.mb_conn.cursor.return_value = mock_cursor

        result = memory_engine.get_article(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_recent_articles(self, memory_engine, mock_db_service):
        """Test recent articles retrieval."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "content": "Content 1", "metadata": '{"title": "Title 1"}'},
            {"id": 2, "content": "Content 2", "metadata": '{"title": "Title 2"}'},
        ]
        mock_db_service.mb_conn.cursor.return_value = mock_cursor

        result = memory_engine.get_recent_articles(limit=5)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    @pytest.mark.asyncio
    async def test_ingest_article_success(self, memory_engine, mock_db_service):
        """Test successful article ingestion."""
        article_payload = {
            "content": "Test content",
            "url": "http://example.com",
            "title": "Test Title",
        }
        statements = []

        with patch("agents.memory.memory_engine.save_article") as mock_save:
            mock_save.return_value = {"status": "saved", "article_id": 1}

            result = memory_engine.ingest_article(article_payload, statements)
            assert result["status"] == "ok"
            assert result["url"] == "http://example.com"

    @pytest.mark.asyncio
    async def test_ingest_handles_nonboolean_nextset_no_loop(
        self, memory_engine, mock_db_service
    ):
        """Ensure ingest_article won't spin if cursor.nextset() returns a non-boolean (e.g. MagicMock).

        Previously cursor.nextset() could return a non-bool MagicMock in tests and cause
        an infinite loop. This regression test simulates that condition and verifies the
        call completes.
        """
        # Prepare a fake tx connection/cursor where nextset returns a MagicMock
        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = {"id": 123}
        fake_cursor.nextset.return_value = MagicMock()  # non-boolean truthy

        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        # Ensure the db service will provide a per-call connection
        mock_db_service.get_connection = MagicMock(return_value=fake_conn)

        # No statements that actually modify DB; use a RETURNING-like statement to hit that code path
        statements = [
            (
                "INSERT INTO sources (id,domain) VALUES (%s,%s) RETURNING id",
                (1, "example.com"),
            )
        ]

        with patch("agents.memory.memory_engine.save_article") as mock_save:
            mock_save.return_value = {"status": "saved", "article_id": 1}
            result = memory_engine.ingest_article(
                {"content": "ok", "url": "http://example.com"}, statements
            )
            assert result["status"] in (
                "ok",
                "error",
            )  # ensure it returns without hanging


class TestMemoryEngineTrainingOperations:
    """Test MemoryEngine training operations."""

    @pytest.mark.asyncio
    async def test_log_training_example_success(self, memory_engine, mock_db_service):
        """Test successful training example logging."""
        task = "summarization"
        input_data = {"text": "Input text"}
        output_data = {"summary": "Output summary"}
        critique = "Good example"

        result = memory_engine.log_training_example(
            task, input_data, output_data, critique
        )
        assert result["status"] == "logged"

    @pytest.mark.asyncio
    async def test_log_training_example_db_failure(
        self, memory_engine, mock_db_service
    ):
        """Test training example logging with database failure."""
        mock_db_service.mb_conn.cursor.side_effect = Exception("DB Error")

        task = "summarization"
        input_data = {"text": "Input text"}
        output_data = {"summary": "Output summary"}
        critique = "Good example"

        result = memory_engine.log_training_example(
            task, input_data, output_data, critique
        )
        assert "error" in result


class TestMemoryEngineStatistics:
    """Test MemoryEngine statistics."""

    @pytest.mark.asyncio
    async def test_get_stats(self, memory_engine, mock_db_service):
        """Test statistics retrieval."""
        # Mock article count query
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"count": 42}
        mock_db_service.mb_conn.cursor.return_value = mock_cursor

        result = memory_engine.get_stats()
        assert result["engine"] == "memory"
        assert result["db_initialized"] is True
        assert result["embedding_model_loaded"] is True
        assert result["article_count"] == 42

    @pytest.mark.asyncio
    async def test_get_article_count(self, memory_engine, mock_db_service):
        """Test article count retrieval."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"count": 100}
        mock_db_service.mb_conn.cursor.return_value = mock_cursor

        result = memory_engine.get_article_count()
        assert result == 100

    @pytest.mark.asyncio
    async def test_get_sources(self, memory_engine, mock_db_service):
        """Test sources retrieval."""
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "url": "http://source1.com",
                "domain": "source1.com",
                "name": "Source 1",
            },
            {
                "id": 2,
                "url": "http://source2.com",
                "domain": "source2.com",
                "name": "Source 2",
            },
        ]
        mock_db_service.mb_conn.cursor.return_value = mock_cursor

        result = memory_engine.get_sources(limit=10)
        assert len(result) == 2
        assert result[0]["name"] == "Source 1"
        assert result[1]["name"] == "Source 2"
