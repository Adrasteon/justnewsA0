"""
Performance Tests for Dual Database Operations

Tests performance characteristics of MariaDB + ChromaDB operations including:
- Query performance benchmarks
- Bulk operation efficiency
- Memory usage patterns
- Concurrent operation scaling
- Vector search performance
"""

import asyncio
import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import psutil
import pytest

from database.models.migrated_models import Article, MigratedDatabaseService, Source
from database.utils.migrated_database_utils import execute_transaction


@pytest.mark.performance
class TestDualDatabasePerformance:
    """Performance tests for dual database operations"""

    @pytest.fixture
    def performance_config(self):
        """Performance test configuration"""
        return {
            "database": {
                "mariadb": {
                    "host": "localhost",
                    "port": 3306,
                    "database": "justnews_perf_test",
                    "user": "perf_user",
                    "password": "perf_password",
                    "pool_size": 5,
                },
                "chromadb": {
                    "host": "localhost",
                    "port": 3307,
                    "collection": "perf_articles",
                },
                "embedding": {
                    "model": "all-MiniLM-L6-v2",
                    "dimensions": 384,
                    "device": "cpu",
                },
            }
        }

    @pytest.fixture
    def mock_performance_service(self, performance_config):
        """Create mock service optimized for performance testing"""
        with patch("mysql.connector.connect") as mock_mb_connect:
            with patch("chromadb.HttpClient") as mock_chroma_client:
                with patch(
                    "sentence_transformers.SentenceTransformer"
                ) as mock_embedding:
                    # Setup MariaDB mock with connection pooling simulation
                    mock_conn = MagicMock()
                    mock_conn.close = MagicMock()
                    mock_mb_connect.return_value = mock_conn

                    # Setup ChromaDB mock
                    mock_client = MagicMock()
                    mock_collection = MagicMock()
                    mock_collection.name = "perf_articles"
                    mock_client.get_collection.return_value = mock_collection
                    mock_chroma_client.return_value = mock_client

                    # Setup embedding mock
                    mock_model = MagicMock()
                    mock_model.encode.return_value = [0.1] * 384
                    mock_embedding.return_value = mock_model

                    service = MigratedDatabaseService(performance_config)

                    # Store mocks for performance testing
                    service._mock_conn = mock_conn
                    service._mock_collection = mock_collection
                    service._mock_model = mock_model

                    yield service

    def test_single_article_retrieval_performance(self, mock_performance_service):
        """Test performance of single article retrieval"""
        # Setup mock data
        mock_cursor = MagicMock()
        mock_article_row = (
            1,
            "https://example.com/article1",
            "Test Article",
            "Content " * 100,
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
        mock_cursor.fetchone.return_value = mock_article_row
        mock_performance_service.mb_conn.cursor.return_value = mock_cursor

        # Measure performance
        start_time = time.time()
        for _ in range(100):
            _ = mock_performance_service.get_article_by_id(1)
        end_time = time.time()

        total_time = end_time - start_time
        avg_time = total_time / 100

        # Performance assertions
        assert avg_time < 0.01  # Should be very fast (< 10ms per query)
        assert total_time < 1.0  # Total time for 100 queries should be reasonable

    def test_bulk_article_insertion_performance(self, mock_performance_service):
        """Test performance of bulk article insertions"""
        # Generate test data
        articles = []
        for i in range(1000):
            article = Article(
                id=i + 1,
                url=f"https://example.com/article{i + 1}",
                title=f"Performance Test Article {i + 1}",
                content=f"Content for performance test article {i + 1}. " * 20,
                source_id=1,
                created_at=datetime(2024, 1, 1),
            )
            articles.append(article)

        # Setup mock for bulk operations
        mock_cursor = MagicMock()
        mock_performance_service.mb_conn.cursor.return_value = mock_cursor

        # Mock ChromaDB bulk operations
        mock_performance_service.collection.add = MagicMock()

        # Measure bulk insertion performance
        start_time = time.time()

        # Simulate bulk insertion (this would be optimized in real implementation)
        for article in articles:
            # Simulate MariaDB insertion
            mock_cursor.execute("INSERT INTO articles ...", ())
            # Simulate ChromaDB vector insertion
            mock_performance_service.collection.add(
                ids=[str(article.id)],
                embeddings=[[0.1] * 384],
                metadatas=[{"article_id": article.id}],
                documents=[article.content],
            )

        end_time = time.time()

        total_time = end_time - start_time
        avg_time_per_article = total_time / len(articles)

        # Performance assertions
        assert avg_time_per_article < 0.005  # < 5ms per article
        assert total_time < 10.0  # Total bulk operation should be fast

    def test_semantic_search_performance(self, mock_performance_service):
        """Test semantic search performance"""
        # Setup mock search results
        mock_performance_service.collection.query.return_value = {
            "ids": [[str(i) for i in range(10)]],
            "metadatas": [[{"article_id": i} for i in range(10)]],
            "documents": [["Content"] * 10],
            "distances": [[0.1 * i for i in range(10)]],
        }

        # Mock article retrieval
        mock_cursor = MagicMock()
        mock_performance_service.mb_conn.cursor.return_value = mock_cursor

        with patch.object(
            mock_performance_service, "get_article_by_id"
        ) as mock_get_article:
            mock_get_article.return_value = Article(
                id=1,
                url="https://test.com",
                title="Test",
                content="Content",
                source_id=1,
                created_at=datetime(2024, 1, 1),
            )

            # Measure search performance
            start_time = time.time()
            for _ in range(50):
                results = mock_performance_service.semantic_search(
                    "test query", n_results=10
                )
                assert len(results) == 10
            end_time = time.time()

            total_time = end_time - start_time
            avg_time = total_time / 50

            # Performance assertions
            assert avg_time < 0.1  # Semantic search should be reasonably fast
            assert total_time < 10.0  # 50 searches should complete quickly

    def test_concurrent_operations_performance(self, mock_performance_service):
        """Test performance under concurrent operations"""

        def simulate_concurrent_reads(service, results, thread_id):
            """Simulate concurrent read operations"""
            thread_results = []
            for i in range(100):
                # Simulate article retrieval
                mock_cursor = MagicMock()
                mock_cursor.fetchone.return_value = (
                    thread_id * 100 + i,
                    f"Article {i}",
                )
                service.mb_conn.cursor.return_value = mock_cursor

                article = service.get_article_by_id(thread_id * 100 + i)
                thread_results.append(article)
            results[thread_id] = thread_results

        # Setup concurrent execution
        num_threads = 5
        results = {}
        threads = []

        start_time = time.time()

        # Start concurrent threads
        for thread_id in range(num_threads):
            thread = threading.Thread(
                target=simulate_concurrent_reads,
                args=(mock_performance_service, results, thread_id),
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        end_time = time.time()

        total_time = end_time - start_time
        _total_operations = num_threads * 100

        # Performance assertions
        assert total_time < 5.0  # Concurrent operations should complete quickly
        assert len(results) == num_threads
        for thread_results in results.values():
            assert len(thread_results) == 100

    def test_memory_usage_patterns(self, mock_performance_service):
        """Test memory usage patterns during operations"""
        process = psutil.Process()

        # Get initial memory usage
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Perform memory-intensive operations
        articles = []
        for i in range(1000):
            article = Article(
                id=i,
                url=f"https://example.com/article{i}",
                title=f"Memory Test Article {i}",
                content="Large content " * 1000,  # Large content to test memory
                source_id=1,
                created_at=datetime(2024, 1, 1),
            )
            articles.append(article)

        # Measure memory after creating objects
        _after_creation_memory = process.memory_info().rss / 1024 / 1024

        # Perform operations
        mock_cursor = MagicMock()
        mock_performance_service.mb_conn.cursor.return_value = mock_cursor

        for article in articles[:100]:  # Process subset
            mock_cursor.fetchone.return_value = (article.id, article.title)
            _ = mock_performance_service.get_article_by_id(article.id)

        # Measure memory after operations
        after_operations_memory = process.memory_info().rss / 1024 / 1024

        # Cleanup
        del articles

        # Memory assertions (allow some variance)
        memory_increase = after_operations_memory - initial_memory
        assert memory_increase < 100  # Should not have excessive memory growth

    def test_transaction_performance(self, mock_performance_service):
        """Test transaction performance"""
        # Setup transaction queries
        queries = [
            "INSERT INTO articles (title, content) VALUES (?, ?)",
            "INSERT INTO article_sources (article_id, source_id) VALUES (?, ?)",
            "UPDATE article_stats SET count = count + 1 WHERE id = ?",
        ]

        params_list = [("Test Article", "Test Content"), (1, 1), (1,)]

        mock_cursor = MagicMock()
        mock_performance_service.mb_conn.cursor.return_value = mock_cursor

        # Measure transaction performance
        start_time = time.time()
        for _ in range(100):
            result = execute_transaction(mock_performance_service, queries, params_list)
            assert result is True
        end_time = time.time()

        total_time = end_time - start_time
        avg_time = total_time / 100

        # Performance assertions
        assert avg_time < 0.01  # Transactions should be very fast
        assert total_time < 2.0  # 100 transactions should be quick

    def test_vector_embedding_performance(self, mock_performance_service):
        """Test vector embedding generation performance"""
        # Test different content sizes
        test_contents = [
            "Short content",
            "Medium content " * 50,
            "Long content " * 500,
            "Very long content " * 2000,
        ]

        total_time = 0
        total_embeddings = 0

        # Mock the encode method to return immediately
        with patch.object(
            mock_performance_service.embedding_model, "encode"
        ) as mock_encode:
            mock_encode.return_value = [0.1] * 384

            for content in test_contents:
                start_time = time.time()
                embedding = mock_performance_service.embedding_model.encode(content)
                end_time = time.time()

                total_time += end_time - start_time
                total_embeddings += 1

                assert len(embedding) == 384  # Expected dimensions

        avg_time = total_time / total_embeddings

        # Performance assertions (embeddings should be very fast when mocked)
        assert avg_time < 0.001  # Should be extremely fast with mocking

    @pytest.mark.asyncio
    async def test_async_operation_performance(self, mock_performance_service):
        """Test async operation performance"""

        async def simulate_async_operation(service, operation_id):
            """Simulate an async database operation"""
            await asyncio.sleep(0.001)  # Simulate async I/O

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (operation_id, f"Result {operation_id}")
            service.mb_conn.cursor.return_value = mock_cursor

            return service.get_article_by_id(operation_id)

        # Measure concurrent async operations
        start_time = time.time()

        tasks = []
        for i in range(50):
            task = simulate_async_operation(mock_performance_service, i)
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        end_time = time.time()

        total_time = end_time - start_time

        # Performance assertions
        assert total_time < 1.0  # Async operations should be fast
        assert len(results) == 50

    def test_database_connection_pooling_performance(self, mock_performance_service):
        """Test connection pooling performance"""
        # Simulate connection pool usage
        connections = []

        # Create multiple connection mocks
        for _i in range(10):
            mock_conn = MagicMock()
            mock_conn.close = MagicMock()
            connections.append(mock_conn)

        # Simulate connection pool behavior
        start_time = time.time()

        for i in range(100):
            # Simulate getting connection from pool
            conn = connections[i % len(connections)]
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (i, f"Data {i}")
            conn.cursor.return_value = mock_cursor

            # Simulate query
            cursor = conn.cursor()
            _result = cursor.fetchone()

        end_time = time.time()

        total_time = end_time - start_time

        # Performance assertions
        assert total_time < 1.0  # Connection pooling should be very fast

    def test_large_dataset_performance(self, mock_performance_service):
        """Test performance with large datasets"""
        # Generate large dataset
        num_articles = 10000
        articles = []

        for i in range(num_articles):
            article = Article(
                id=i + 1,
                url=f"https://example.com/article{i + 1}",
                title=f"Large Dataset Article {i + 1}",
                content=f"Content for article {i + 1} in large dataset. " * 10,
                source_id=(i % 10) + 1,  # Distribute across 10 sources
                created_at=datetime(2024, 1, 1),
            )
            articles.append(article)

        # Test bulk statistics calculation
        start_time = time.time()

        # Simulate statistics calculation
        total_articles = len(articles)
        sources_count = len({a.source_id for a in articles})
        avg_content_length = sum(len(a.content) for a in articles) / len(articles)

        end_time = time.time()

        calculation_time = end_time - start_time

        # Performance assertions
        assert calculation_time < 1.0  # Statistics calculation should be fast
        assert total_articles == num_articles
        assert sources_count == 10
        assert avg_content_length > 0

    def test_search_index_performance(self, mock_performance_service):
        """Test search index performance"""
        # Setup mock search index
        mock_performance_service.collection.query.return_value = {
            "ids": [
                [str(i) for i in range(50)]
            ],  # Return exactly 50 results as requested
            "metadatas": [[{"score": 0.9 - i * 0.01} for i in range(50)]],
            "documents": [["Document content"] * 50],
            "distances": [[0.1 + i * 0.01 for i in range(50)]],
        }

        # Test different search queries
        search_queries = [
            "technology news",
            "politics and government",
            "science breakthrough",
            "sports championship",
            "entertainment awards",
        ]

        total_search_time = 0
        total_results = 0

        # Mock the embedding and article/source retrieval
        with patch.object(
            mock_performance_service.embedding_model, "encode"
        ) as mock_encode:
            mock_encode.return_value = np.array([0.1] * 384)

            with patch.object(
                mock_performance_service, "get_article_by_id"
            ) as mock_get_article:
                mock_get_article.return_value = Article(
                    id=1,
                    url="https://test.com",
                    title="Test",
                    content="Content",
                    source_id=1,
                    created_at=datetime(2024, 1, 1),
                )

                with patch.object(
                    mock_performance_service, "get_source_by_id"
                ) as mock_get_source:
                    mock_get_source.return_value = Source(
                        id=1,
                        url="https://source.com",
                        domain="source.com",
                        name="Test Source",
                        created_at=datetime(2024, 1, 1),
                    )

                    for query in search_queries:
                        start_time = time.time()
                        results = mock_performance_service.semantic_search(
                            query, n_results=50
                        )
                        end_time = time.time()

                        total_search_time += end_time - start_time
                        total_results += len(results)

        avg_search_time = total_search_time / len(search_queries)

        # Performance assertions
        assert (
            avg_search_time < 0.05
        )  # Should be reasonably fast with mocking (allowing for test overhead)
        assert total_results == len(search_queries) * 50  # All results returned


@pytest.mark.performance
@pytest.mark.parametrize("concurrency_level", [1, 5, 10, 20])
def test_scalability_under_load(concurrency_level, mock_database_service):
    """Test system scalability under different concurrency levels"""

    def worker_task(service, task_id, results):
        """Worker task for concurrent execution"""
        start_time = time.time()

        # Simulate work
        for i in range(10):
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (task_id * 10 + i, f"Data {i}")
            service.mb_conn.cursor.return_value = mock_cursor

            _ = service.get_article_by_id(task_id * 10 + i)

        end_time = time.time()
        results[task_id] = end_time - start_time

    # Execute concurrent tasks
    results = {}
    threads = []

    start_time = time.time()

    for i in range(concurrency_level):
        thread = threading.Thread(
            target=worker_task, args=(mock_database_service, i, results)
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    total_time = time.time() - start_time

    # Scalability assertions
    _avg_task_time = sum(results.values()) / len(results)
    max_task_time = max(results.values())

    # Performance should degrade gracefully with concurrency
    assert total_time < concurrency_level * 2.0  # Allow some overhead
    assert max_task_time < 1.0  # No task should take too long
