"""
Tests for JustNews Analyst Agent
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from agents.analyst.tools import (
    analyze_content_trends,
    analyze_text_statistics,
    extract_key_metrics,
    get_analyst_engine,
    identify_entities,
    log_feedback,
    process_analysis_request,
)


class TestAnalystTools:
    """Test analyst agent tools"""

    def test_get_analyst_engine_singleton(self):
        """Test that get_analyst_engine returns singleton instance"""
        with patch("agents.analyst.tools.AnalystEngine") as mock_engine_class:
            mock_engine = Mock()
            mock_engine_class.return_value = mock_engine

            # Reset global engine
            import agents.analyst.tools

            agents.analyst.tools._engine = None

            engine1 = get_analyst_engine()
            engine2 = get_analyst_engine()

            assert engine1 is engine2
            assert engine1 is mock_engine
            mock_engine_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_analysis_request_sentiment(self):
        """Test processing sentiment analysis request"""
        mock_engine = Mock()
        mock_engine.analyze_sentiment.return_value = {
            "sentiment": "positive",
            "confidence": 0.85,
            "scores": {"positive": 0.8, "negative": 0.1, "neutral": 0.1},
        }

        with patch("agents.analyst.tools.get_analyst_engine", return_value=mock_engine):
            result = await process_analysis_request(
                text="This is great news!", analysis_type="sentiment"
            )

            assert result["sentiment"] == "positive"
            assert result["confidence"] == 0.85
            mock_engine.analyze_sentiment.assert_called_once_with("This is great news!")

    @pytest.mark.asyncio
    async def test_process_analysis_request_entities(self):
        """Test processing entity extraction request"""
        mock_engine = Mock()
        mock_engine.extract_entities.return_value = {
            "entities": [
                {"text": "Apple", "type": "ORG", "confidence": 0.9},
                {"text": "Tim Cook", "type": "PERSON", "confidence": 0.8},
            ]
        }

        with patch("agents.analyst.tools.get_analyst_engine", return_value=mock_engine):
            result = await process_analysis_request(
                text="Apple CEO Tim Cook announced new products.",
                analysis_type="entities",
            )

            assert len(result["entities"]) == 2
            assert result["entities"][0]["text"] == "Apple"
            mock_engine.extract_entities.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_analysis_request_statistics(self):
        """Test processing text statistics request"""
        mock_engine = Mock()
        mock_engine.analyze_text_statistics.return_value = {
            "word_count": 25,
            "sentence_count": 3,
            "avg_word_length": 4.5,
            "readability_score": 65.2,
        }

        with patch("agents.analyst.tools.get_analyst_engine", return_value=mock_engine):
            result = await process_analysis_request(
                text="This is a sample text for analysis.", analysis_type="statistics"
            )

            assert result["word_count"] == 25
            assert result["sentence_count"] == 3
            mock_engine.analyze_text_statistics.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_analysis_request_unknown_type(self):
        """Test processing request with unknown analysis type"""
        mock_engine = Mock()

        with patch("agents.analyst.tools.get_analyst_engine", return_value=mock_engine):
            result = await process_analysis_request(
                text="Sample text", analysis_type="unknown"
            )

            assert result["error"] == "Unknown analysis type: unknown"
            assert result["supported_types"] == [
                "sentiment",
                "entities",
                "statistics",
                "metrics",
                "bias",
                "sentiment_and_bias",
            ]

    @pytest.mark.asyncio
    async def test_process_analysis_request_engine_error(self):
        """Test handling engine errors"""
        mock_engine = Mock()
        mock_engine.analyze_sentiment.side_effect = Exception("Engine error")

        with patch("agents.analyst.tools.get_analyst_engine", return_value=mock_engine):
            result = await process_analysis_request(
                text="Sample text", analysis_type="sentiment"
            )

            assert result["error"] == "Engine error"
            assert "Engine error" in result["details"]

    def test_identify_entities(self):
        """Test entity identification wrapper"""
        with patch("agents.analyst.tools.get_analyst_engine") as mock_get_engine:
            mock_engine = Mock()
            mock_engine.extract_entities.return_value = [
                {"text": "Google", "type": "ORG"},
                {"text": "New York", "type": "LOC"},
            ]
            mock_get_engine.return_value = mock_engine

            result = identify_entities("Google is based in New York.")

            assert len(result) == 2
            assert result[0]["text"] == "Google"
            mock_engine.extract_entities.assert_called_once()

    def test_analyze_text_statistics(self):
        """Test text statistics analysis wrapper"""
        with patch("agents.analyst.tools.get_analyst_engine") as mock_get_engine:
            mock_engine = Mock()
            mock_engine.analyze_text_statistics.return_value = {
                "word_count": 10,
                "sentence_count": 2,
                "readability": 75.5,
            }
            mock_get_engine.return_value = mock_engine

            result = analyze_text_statistics("This is a test. It has two sentences.")

            assert result["word_count"] == 10
            assert result["sentence_count"] == 2
            mock_engine.analyze_text_statistics.assert_called_once()

    def test_extract_key_metrics(self):
        """Test key metrics extraction wrapper"""
        with patch("agents.analyst.tools.get_analyst_engine") as mock_get_engine:
            mock_engine = Mock()
            mock_engine.extract_key_metrics.return_value = {
                "metrics": {"sentiment_score": 0.7, "complexity_score": 0.5},
                "total_metrics": 2,
                "text_length": 30,
            }
            mock_get_engine.return_value = mock_engine

            result = extract_key_metrics("Positive news about technology.")

            assert result["metrics"]["sentiment_score"] == 0.7
            mock_engine.extract_key_metrics.assert_called_once()

    def test_analyze_content_trends(self):
        """Test content trends analysis wrapper"""
        with patch("agents.analyst.tools.get_analyst_engine") as mock_get_engine:
            mock_engine = Mock()
            mock_engine.analyze_content_trends.return_value = {
                "trends": {
                    "topics": ["technology", "business"],
                    "sentiment_trend": "increasing",
                },
                "total_texts": 3,
                "total_trends": 2,
            }
            mock_get_engine.return_value = mock_engine

            articles = ["Article 1", "Article 2", "Article 3"]
            result = analyze_content_trends(articles)

            assert "technology" in result["trends"]["topics"]
            mock_engine.analyze_content_trends.assert_called_once()

    def test_log_feedback(self):
        """Test feedback logging"""
        with patch("agents.analyst.tools.logger") as mock_logger:
            feedback_data = {
                "analysis_type": "sentiment",
                "accuracy": 0.9,
                "user_rating": 4,
            }

            log_feedback("sentiment", feedback_data)

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args[0][0]
            assert "sentiment" in call_args


class TestAnalystMainApp:
    """Test analyst agent FastAPI application"""

    def test_app_creation(self):
        """Test that the FastAPI app can be created"""
        with (
            patch("agents.analyst.main.JustNewsMetrics"),
            patch("agents.analyst.main.create_database_service"),
            patch("agents.analyst.main.get_logger"),
        ):
            from agents.analyst.main import app

            assert app is not None
            assert hasattr(app, "routes")

    @patch("agents.analyst.main.validate_content_size")
    @patch("agents.analyst.main.sanitize_content")
    @patch("agents.analyst.main.analyze_text_statistics")
    def test_analyze_endpoint_statistics(
        self, mock_analyze, mock_sanitize, mock_validate
    ):
        """Test the /analyze_text_statistics endpoint"""
        mock_validate.return_value = True
        mock_sanitize.return_value = "sanitized content"
        mock_analyze.return_value = {"word_count": 10, "sentence_count": 2}

        with (
            patch("agents.analyst.main.JustNewsMetrics"),
            patch("agents.analyst.main.create_database_service"),
            patch("agents.analyst.main.get_logger"),
        ):
            from agents.analyst.main import app

            client = TestClient(app)

            response = client.post(
                "/analyze_text_statistics",
                json={"args": [], "kwargs": {"text": "Test content for analysis."}},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["word_count"] == 10
            assert data["sentence_count"] == 2

    @patch("agents.analyst.main.validate_content_size")
    def test_analyze_endpoint_content_too_large(self, mock_validate):
        """Test handling of content that exceeds size limits"""
        mock_validate.return_value = False

        with (
            patch("agents.analyst.main.JustNewsMetrics"),
            patch("agents.analyst.main.create_database_service"),
            patch("agents.analyst.main.get_logger"),
        ):
            from agents.analyst.main import app

            client = TestClient(app)

            large_content = "x" * 2000000  # 2MB content
            response = client.post(
                "/analyze_text_statistics",
                json={"args": [], "kwargs": {"text": large_content}},
            )

            assert response.status_code == 500
            assert (
                "Content size exceeds maximum allowed limit"
                in response.json()["detail"]
            )

    @patch("agents.analyst.main.identify_entities")
    def test_analyze_endpoint_entities(self, mock_identify):
        """Test the /analyze/entities endpoint"""
        mock_identify.return_value = [
            {"text": "Apple", "type": "ORG", "confidence": 0.9}
        ]

        with (
            patch("agents.analyst.main.JustNewsMetrics"),
            patch("agents.analyst.main.create_database_service"),
            patch("agents.analyst.main.get_logger"),
            patch("agents.analyst.main.validate_content_size", return_value=True),
            patch("agents.analyst.main.sanitize_content", return_value="sanitized"),
        ):
            from agents.analyst.main import app

            client = TestClient(app)

            response = client.post(
                "/identify_entities",
                json={"args": [], "kwargs": {"text": "Apple announced new products."}},
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["text"] == "Apple"

    def test_health_endpoint(self):
        """Test the /health endpoint"""
        with (
            patch("agents.analyst.main.JustNewsMetrics"),
            patch("agents.analyst.main.create_database_service"),
            patch("agents.analyst.main.get_logger"),
        ):
            from agents.analyst.main import app

            client = TestClient(app)

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"

    def test_metrics_endpoint(self):
        """Test the /metrics endpoint"""
        with (
            patch("agents.analyst.main.JustNewsMetrics") as mock_metrics_class,
            patch("agents.analyst.main.create_database_service"),
            patch("agents.analyst.main.get_logger"),
        ):
            mock_metrics = Mock()
            mock_metrics.get_metrics.return_value = "# Prometheus metrics"
            mock_metrics_class.return_value = mock_metrics

            from agents.analyst.main import app

            client = TestClient(app)

            response = client.get("/metrics")

            assert response.status_code == 200
            assert "HELP" in response.text  # Prometheus format includes HELP comments
