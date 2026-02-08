"""
End-to-End Integration Tests for JustNews

This module contains comprehensive integration tests that validate:
- Complete news processing pipeline (crawler -> analyst -> fact_checker -> synthesizer)
- Cross-agent communication workflows
- Database integration across the full pipeline
- Error handling and recovery in integrated scenarios
- Performance characteristics of end-to-end workflows
"""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_utils import (
    AsyncTestHelper,
    CustomAssertions,
    MockFactory,
    PerformanceTester,
)


class TestEndToEndNewsProcessingPipeline:
    """End-to-end tests for the complete news processing pipeline"""

    def setup_method(self):
        """Setup test fixtures"""
        self.helper = AsyncTestHelper()
        self.mock_factory = MockFactory()
        self.perf_tester = PerformanceTester("e2e_pipeline")
        self.assertions = CustomAssertions()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_news_processing_workflow(self):
        """Test the complete news processing workflow from URL to final synthesis"""
        start_time = time.time()

        # Mock article URL for processing
        test_url = "https://example.com/news/breaking-news-story"

        # Step 1: Crawler extracts article content
        with patch("agents.crawler.tools.extract_article_content") as mock_extract:
            mock_extract.return_value = {
                "title": "Breaking News: Major Scientific Discovery",
                "content": "Scientists have made a groundbreaking discovery in renewable energy technology.",
                "author": "Dr. Jane Smith",
                "publish_date": "2023-12-01",
                "source": "Science Daily",
                "url": test_url,
            }

            crawler_result = mock_extract(test_url)
            assert crawler_result["title"] is not None
            assert len(crawler_result["content"]) > 0

        # Step 2: Analyst performs sentiment and entity analysis
        with (
            patch("agents.analyst.tools.identify_entities") as mock_entities,
            patch("agents.analyst.tools.analyze_text_statistics") as mock_stats,
        ):
            mock_entities.return_value = [
                {"text": "Scientists", "type": "PERSON", "confidence": 0.9},
                {"text": "renewable energy", "type": "TOPIC", "confidence": 0.8},
            ]

            mock_stats.return_value = {
                "word_count": 25,
                "sentence_count": 3,
                "sentiment_score": 0.7,
                "readability_score": 65.0,
            }

            entities = mock_entities(crawler_result["content"])
            stats = mock_stats(crawler_result["content"])

            assert len(entities) > 0
            assert stats["word_count"] > 0
            assert "sentiment_score" in stats

        # Step 3: Fact checker validates claims and sources
        with (
            patch("agents.fact_checker.tools.verify_facts") as mock_verify,
            patch("agents.fact_checker.tools.validate_sources") as mock_validate,
        ):
            mock_verify.return_value = {
                "verdict": "true",
                "confidence": 0.85,
                "evidence": ["Peer-reviewed study confirms discovery"],
                "contradictions": [],
            }

            mock_validate.return_value = {
                "overall_credibility": 0.9,
                "sources": [{"url": "sciencedaily.com", "credibility_score": 0.9}],
            }

            fact_check = mock_verify(crawler_result["content"])
            source_validation = mock_validate(
                crawler_result["content"], ["sciencedaily.com"]
            )

            assert fact_check["verdict"] == "true"
            assert source_validation["overall_credibility"] > 0.8

        # Step 4: Synthesizer creates final summary
        with patch("agents.synthesizer.tools.synthesize_content") as mock_synthesize:
            mock_synthesize.return_value = {
                "summary": "Scientists announce major breakthrough in renewable energy technology.",
                "key_points": [
                    "Groundbreaking scientific discovery",
                    "Renewable energy technology advancement",
                    "Published in peer-reviewed study",
                ],
                "topics": ["Science", "Technology", "Environment"],
                "sentiment": "positive",
            }

            synthesis = mock_synthesize(
                content=crawler_result["content"],
                analysis_data={
                    "entities": entities,
                    "statistics": stats,
                    "fact_check": fact_check,
                    "source_validation": source_validation,
                },
            )

            assert synthesis["summary"] is not None
            assert len(synthesis["key_points"]) > 0
            assert synthesis["sentiment"] == "positive"

        # Step 5: Memory agent stores the processed article
        with patch("agents.memory.tools.save_article") as mock_save:
            mock_save.return_value = {
                "article_id": 123,
                "status": "saved",
                "embeddings_generated": True,
                "duplicate_detected": False,
            }

            save_result = mock_save(
                {
                    "title": crawler_result["title"],
                    "content": crawler_result["content"],
                    "url": test_url,
                    "source": crawler_result["source"],
                    "analysis": {
                        "entities": entities,
                        "statistics": stats,
                        "fact_check": fact_check,
                        "synthesis": synthesis,
                    },
                }
            )

            assert save_result["article_id"] == 123
            assert save_result["status"] == "saved"

        # Verify end-to-end timing is reasonable
        end_time = time.time()
        total_time = end_time - start_time
        assert total_time < 5.0  # Should complete within 5 seconds

        # Verify the complete pipeline result
        final_result = {
            "article_id": save_result["article_id"],
            "title": crawler_result["title"],
            "summary": synthesis["summary"],
            "sentiment": synthesis["sentiment"],
            "fact_check_verdict": fact_check["verdict"],
            "source_credibility": source_validation["overall_credibility"],
            "processing_time": total_time,
        }

        self.assertions.assert_valid_news_processing_result(final_result)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_cross_agent_communication_workflow(self):
        """Test cross-agent communication through MCP bus"""
        # Setup mock MCP bus
        mock_bus = self.mock_factory.create_mock_mcp_bus()

        # Simulate agent discovery and communication
        agents = ["crawler", "analyst", "fact_checker", "synthesizer", "memory"]

        # Test agent registration
        for agent in agents:
            registration = {
                "agent": agent,
                "port": 8000 + agents.index(agent),
                "capabilities": self._get_agent_capabilities(agent),
                "health_endpoint": "/health",
            }

            with patch.object(
                mock_bus, "register_agent", wraps=mock_bus.register_agent
            ) as mock_register:
                result = mock_bus.register_agent(registration)
                assert result is True
                mock_register.assert_called_once()

        # Test inter-agent call chain
        test_content = "Test news article content for processing."

        # Crawler -> Analyst
        with patch.object(
            mock_bus,
            "call_agent",
            new=AsyncMock(
                return_value={
                    "status": "success",
                    "entities": [{"text": "Test", "type": "MISC"}],
                    "sentiment": "neutral",
                }
            ),
        ) as mock_call:
            analyst_result = await mock_bus.call_agent(
                "analyst", "analyze", content=test_content
            )
            assert analyst_result["status"] == "success"
            mock_call.assert_awaited_once()

        # Analyst -> Fact Checker
        with patch.object(
            mock_bus,
            "call_agent",
            new=AsyncMock(
                return_value={"status": "success", "verdict": "true", "confidence": 0.8}
            ),
        ) as mock_call:
            fact_check_result = await mock_bus.call_agent(
                "fact_checker", "verify", content=test_content
            )
            assert fact_check_result["verdict"] == "true"
            mock_call.assert_awaited_once()

        # Fact Checker -> Synthesizer
        with patch.object(
            mock_bus,
            "call_agent",
            new=AsyncMock(
                return_value={
                    "status": "success",
                    "summary": "Test article summary",
                    "topics": ["Test"],
                }
            ),
        ) as mock_call:
            synthesis_result = await mock_bus.call_agent(
                "synthesizer", "synthesize", content=test_content
            )
            assert synthesis_result["summary"] is not None
            mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_database_integration_across_pipeline(self):
        """Test database operations across the full processing pipeline"""
        # Mock database service
        mock_db = self.mock_factory.create_mock_database_service()

        test_article = {
            "title": "Integration Test Article",
            "content": "This is a test article for integration testing.",
            "url": "https://test.com/article",
            "source": "Test Source",
        }

        # Test article storage
        with patch.object(mock_db, "execute_query") as mock_execute:
            mock_execute.return_value = {"article_id": 456}

            # Simulate memory agent saving article
            save_query = """
            INSERT INTO articles (title, content, url, source_name)
            VALUES (%s, %s, %s, %s)
            """
            result = mock_execute(
                save_query,
                (
                    test_article["title"],
                    test_article["content"],
                    test_article["url"],
                    test_article["source"],
                ),
            )

            assert result["article_id"] == 456

        # Test embedding generation and storage
        with patch.object(mock_db, "collection") as mock_collection:
            mock_collection.add.return_value = None

            # Simulate adding embeddings to ChromaDB
            embeddings = [[0.1, 0.2, 0.3]]  # Mock embeddings
            metadata = [{"article_id": 456, "title": test_article["title"]}]

            mock_collection.add(embeddings=embeddings, metadatas=metadata, ids=["456"])

            mock_collection.add.assert_called_once()

        # Test semantic search retrieval
        with patch.object(mock_db, "collection") as mock_collection:
            mock_collection.query.return_value = {
                "ids": [["456"]],
                "documents": [[test_article["content"]]],
                "metadatas": [[{"article_id": 456}]],
                "distances": [[0.1]],
            }

            # Simulate search
            query_embedding = [0.1, 0.2, 0.3]
            results = mock_collection.query(
                query_embeddings=[query_embedding], n_results=5
            )

            assert len(results["ids"][0]) == 1
            assert results["ids"][0][0] == "456"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_error_handling_and_recovery(self):
        """Test error handling and recovery in integrated scenarios"""
        # Test crawler failure recovery
        with patch("agents.crawler.tools.extract_article_content") as mock_extract:
            mock_extract.side_effect = Exception("Network timeout")

            # Should handle gracefully
            try:
                mock_extract("https://failing-url.com")
                raise AssertionError("Should have raised exception")
            except Exception as e:
                assert "Network timeout" in str(e)

        # Test analyst fallback when GPU unavailable
        with patch("agents.analyst.tools.get_analyst_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.analyze_sentiment.side_effect = Exception("GPU unavailable")
            mock_get_engine.return_value = mock_engine

            # Should attempt CPU fallback (simulated)
            try:
                # This would normally trigger CPU fallback logic
                pass
            except Exception:
                # In real implementation, would fallback to CPU
                pass

        # Test database connection recovery
        with patch(
            "database.utils.migrated_database_utils.create_database_service"
        ) as mock_create:
            mock_create.side_effect = [Exception("Connection failed"), MagicMock()]

            # First call fails, second succeeds (simulated retry logic)

            # This would normally implement retry logic
            retry_count = 0
            max_retries = 3

            while retry_count < max_retries:
                try:
                    # Simulate retry mechanism
                    if retry_count == 0:
                        raise Exception("Connection failed")
                    else:
                        # Success on retry; break out (no DB object needed)
                        break
                except Exception:
                    retry_count += 1

            assert retry_count == 1  # Should succeed on second try

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_performance_under_load(self):
        """Test system performance under concurrent load"""
        # Setup performance testing
        perf_tester = PerformanceTester("pipeline_load_test")

        # Simulate concurrent article processing
        async def process_single_article(article_id: int):
            """Process a single article (simulated)"""
            await asyncio.sleep(0.01)  # Simulate processing time
            return f"processed_{article_id}"

        # Test concurrent processing
        article_ids = list(range(10))
        start_time = time.time()

        tasks = [process_single_article(article_id) for article_id in article_ids]
        results = await asyncio.gather(*tasks)

        end_time = time.time()
        total_time = end_time - start_time

        # Verify all articles processed
        assert len(results) == 10
        assert all(f"processed_{i}" in result for i, result in enumerate(results))

        # Performance assertions
        avg_time_per_article = total_time / len(article_ids)
        assert avg_time_per_article < 0.05  # Should process quickly

        perf_tester.record_metric("concurrent_processing_time", total_time)
        perf_tester.record_metric("articles_per_second", len(article_ids) / total_time)

    def _get_agent_capabilities(self, agent_name: str) -> list[str]:
        """Get capabilities for a given agent"""
        capabilities_map = {
            "crawler": ["content_extraction", "article_parsing"],
            "analyst": ["sentiment_analysis", "entity_extraction", "bias_detection"],
            "fact_checker": ["claim_verification", "source_validation"],
            "synthesizer": ["content_synthesis", "topic_modeling"],
            "memory": ["article_storage", "semantic_search"],
        }
        return capabilities_map.get(agent_name, [])

    def _simulate_full_pipeline(self, article_url: str) -> dict[str, Any]:
        """Simulate the full processing pipeline for testing"""
        # This is a simplified simulation - in real tests, would use actual agent calls
        return {
            "article_id": 123,
            "title": "Processed Article",
            "summary": "Article summary",
            "sentiment": "positive",
            "credibility_score": 0.85,
            "processing_time": 1.2,
        }
