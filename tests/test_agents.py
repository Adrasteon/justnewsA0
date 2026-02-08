"""
Agent Testing Framework

This module provides comprehensive testing patterns and utilities for testing
JustNews components. It includes:

- Base test classes for different agent types
- Common testing patterns and fixtures
- Mock agents and MCP communication
- Performance testing for agents
- Integration testing helpers

All tests follow clean repository patterns and are designed for
production-ready agent testing.
"""

from collections.abc import Callable
from typing import Any

import pytest
import pytest_asyncio

from tests.test_utils import (
    AsyncTestHelper,
    CustomAssertions,
    MockFactory,
    PerformanceTester,
    TestConfig,
    TestDataGenerator,
)

# ============================================================================
# BASE TEST CLASSES
# ============================================================================


class BaseAgentTest:
    """Base class for agent testing"""

    @pytest.fixture(autouse=True)
    def setup_agent_test(self, mock_mcp_bus_response):
        """Setup common agent test fixtures"""
        self.mock_bus = MockFactory.create_mock_mcp_bus()
        self.sample_articles = TestDataGenerator.generate_articles(3)
        self.mock_response = mock_mcp_bus_response

    def assert_agent_response_valid(
        self, response: dict, expected_keys: list[str] | None = None
    ):
        """Assert that agent response follows expected structure"""
        CustomAssertions.assert_mcp_response_valid(response)

        # If specific keys are expected, check for them
        if expected_keys:
            data = response.get("data", {})
            for key in expected_keys:
                assert key in data, f"Expected key '{key}' not found in response data"
        else:
            # Default check for expected content keys
            expected_keys = [
                "sentiment",
                "verdict",
                "summary",
                "entities",
                "topics",
                "credibility_score",
                "agents",
            ]
            assert "result" in response.get("data", {}) or any(
                key in response.get("data", {}) for key in expected_keys
            ), (
                f"Response data missing expected content. Expected one of: {expected_keys}"
            )

    async def call_agent_tool(self, agent_name: str, tool_name: str, **kwargs):
        """Helper to call agent tool through mock bus"""
        return await self.mock_bus.call_agent(agent_name, tool_name, **kwargs)


class AsyncAgentTest(BaseAgentTest):
    """Base class for async agent testing"""

    @pytest_asyncio.fixture
    async def async_agent_setup(self):
        """Async setup for agent tests"""
        yield

    async def assert_async_agent_operation(
        self, operation: Callable, timeout: float = 5.0
    ):
        """Assert async agent operation completes successfully"""
        await AsyncTestHelper.assert_eventually_true(
            lambda: True,  # Placeholder - implement actual condition
            timeout=timeout,
            message="Agent operation did not complete",
        )


# ============================================================================
# AGENT-SPECIFIC TEST CLASSES
# ============================================================================


class TestAnalystAgent(AsyncAgentTest):
    """Test class for Analyst agent"""

    @pytest.mark.asyncio
    async def test_sentiment_analysis(self, sample_articles):
        """Test sentiment analysis functionality"""
        for article in sample_articles:
            response = await self.call_agent_tool(
                "analyst", "analyze_sentiment", content=article["content"]
            )

            self.assert_agent_response_valid(response)
            data = response["data"]
            assert "sentiment" in data
            assert "confidence" in data
            assert data["sentiment"] in ["positive", "negative", "neutral"]

    @pytest.mark.asyncio
    async def test_entity_extraction(self, sample_articles):
        """Test entity extraction functionality"""
        article = sample_articles[0]
        response = await self.call_agent_tool(
            "analyst", "extract_entities", content=article["content"]
        )

        self.assert_agent_response_valid(response)
        data = response["data"]
        assert "entities" in data
        assert isinstance(data["entities"], list)

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_analyst_performance(self, performance_timer):
        """Test analyst performance requirements"""
        tester = PerformanceTester("sentiment_analysis")

        async def analyze_sample():
            return await self.call_agent_tool(
                "analyst",
                "analyze_sentiment",
                content="Sample news content for performance testing.",
            )

        metrics = await tester.measure_async_operation(analyze_sample, iterations=5)
        metrics.assert_performance_requirements(max_average_time=1.0)


class TestFactCheckerAgent(AsyncAgentTest):
    """Test class for Fact Checker agent"""

    @pytest.mark.asyncio
    async def test_fact_verification(self, sample_articles):
        """Test fact verification functionality"""
        article = sample_articles[0]
        response = await self.call_agent_tool(
            "fact_checker", "verify_facts", content=article["content"]
        )

        self.assert_agent_response_valid(response)
        data = response["data"]
        assert "verdict" in data
        assert "confidence" in data
        assert data["verdict"] in ["verified", "false", "questionable"]

    @pytest.mark.asyncio
    async def test_source_credibility(self, sample_articles):
        """Test source credibility assessment"""
        response = await self.call_agent_tool(
            "fact_checker", "assess_credibility", source="reputable-news.com"
        )

        self.assert_agent_response_valid(response)
        data = response["data"]
        assert "credibility_score" in data
        assert 0.0 <= data["credibility_score"] <= 1.0


class TestSynthesizerAgent(AsyncAgentTest):
    """Test class for Synthesizer agent"""

    @pytest.mark.asyncio
    async def test_content_synthesis(self, sample_articles):
        """Test content synthesis functionality"""
        articles_content = [art["content"] for art in sample_articles]
        response = await self.call_agent_tool(
            "synthesizer",
            "synthesize_summary",
            articles=articles_content,
            max_length=100,
        )

        self.assert_agent_response_valid(response)
        data = response["data"]
        assert "summary" in data
        assert isinstance(data["summary"], str)
        assert len(data["summary"]) <= 100

    @pytest.mark.asyncio
    async def test_topic_modeling(self, sample_articles):
        """Test topic modeling functionality"""
        articles_content = [art["content"] for art in sample_articles]
        response = await self.call_agent_tool(
            "synthesizer", "extract_topics", articles=articles_content
        )

        self.assert_agent_response_valid(response)
        data = response["data"]
        assert "topics" in data
        assert isinstance(data["topics"], list)


# ============================================================================
# MCP COMMUNICATION TESTS
# ============================================================================


class TestMCPCommunication(BaseAgentTest):
    """Test MCP Bus communication patterns"""

    @pytest.mark.asyncio
    async def test_agent_registration(self):
        """Test agent registration with MCP Bus"""
        # This would test actual MCP Bus integration
        # For now, test the mock implementation
        agents = self.mock_bus.agents
        assert "analyst" in agents
        assert "fact_checker" in agents
        assert "synthesizer" in agents

    @pytest.mark.asyncio
    async def test_agent_discovery(self):
        """Test agent discovery through MCP Bus"""
        response = await self.call_agent_tool("mcp_bus", "list_agents")
        self.assert_agent_response_valid(response)
        data = response["data"]
        assert "agents" in data
        assert isinstance(data["agents"], list)

    @pytest.mark.asyncio
    async def test_tool_call_routing(self):
        """Test that tool calls are routed correctly"""
        response = await self.call_agent_tool(
            "analyst", "analyze_sentiment", content="test"
        )
        self.assert_agent_response_valid(response)

        # Verify call was recorded
        calls = self.mock_bus.get_call_history()
        assert len(calls) > 0
        assert calls[-1]["agent"] == "analyst"
        assert calls[-1]["tool"] == "analyze_sentiment"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestAgentIntegration(AsyncAgentTest):
    """Integration tests for agent workflows"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_news_analysis_pipeline(self, sample_articles):
        """Test complete news analysis pipeline"""
        article = sample_articles[0]

        # Step 1: Sentiment analysis
        sentiment_response = await self.call_agent_tool(
            "analyst", "analyze_sentiment", content=article["content"]
        )
        self.assert_agent_response_valid(sentiment_response)

        # Step 2: Fact checking
        fact_response = await self.call_agent_tool(
            "fact_checker", "verify_facts", content=article["content"]
        )
        self.assert_agent_response_valid(fact_response)

        # Step 3: Synthesis
        synthesis_response = await self.call_agent_tool(
            "synthesizer",
            "synthesize_summary",
            articles=[article["content"]],
            sentiment=sentiment_response["data"]["sentiment"],
        )
        self.assert_agent_response_valid(synthesis_response)

        # Verify pipeline coherence
        assert synthesis_response["data"]["summary"] is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_agent_error_handling(self):
        """Test error handling across agents"""
        # Test with invalid input
        response = await self.call_agent_tool(
            "analyst",
            "analyze_sentiment",
            content="",  # Empty content
        )

        # Should still return valid response structure
        self.assert_agent_response_valid(response)
        # But may indicate error or default behavior


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


class TestAgentPerformance(BaseAgentTest):
    """Performance tests for agents"""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_agent_response_times(self):
        """Test that agents respond within acceptable time limits"""
        tester = PerformanceTester("agent_response")

        async def measure_response():
            return await self.call_agent_tool(
                "analyst", "analyze_sentiment", content="Performance test content."
            )

        metrics = await tester.measure_async_operation(measure_response, iterations=10)
        metrics.assert_performance_requirements(max_average_time=0.5, max_p95_time=1.0)

    @pytest.mark.performance
    @pytest.mark.gpu
    @pytest.mark.asyncio
    async def test_gpu_accelerated_performance(self):
        """Test GPU-accelerated agent performance"""
        if not TestConfig.is_gpu_available():
            pytest.skip("GPU not available for testing")

        # Test GPU-specific performance
        tester = PerformanceTester("gpu_analysis")

        async def gpu_operation():
            return await self.call_agent_tool(
                "analyst", "gpu_analyze", content="GPU performance test content."
            )

        metrics = await tester.measure_async_operation(gpu_operation, iterations=5)
        # GPU operations should be faster
        metrics.assert_performance_requirements(max_average_time=0.2)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def parametrize_agent_tests(*agent_tools):
    """Parametrize tests across multiple agent tools"""
    return pytest.mark.parametrize(
        "agent,tool",
        agent_tools,
        ids=[f"{agent}_{tool}" for agent, tool in agent_tools],
    )


def create_agent_test_data(agent_type: str) -> dict[str, Any]:
    """Create test data specific to agent type"""
    test_data = {
        "analyst": {
            "content": "Sample news content for analysis.",
            "expected_tools": ["analyze_sentiment", "extract_entities"],
        },
        "fact_checker": {
            "content": "Factual statement to verify.",
            "expected_tools": ["verify_facts", "assess_credibility"],
        },
        "synthesizer": {
            "articles": ["Article 1 content", "Article 2 content"],
            "expected_tools": ["synthesize_summary", "extract_topics"],
        },
    }

    return test_data.get(agent_type, {})
