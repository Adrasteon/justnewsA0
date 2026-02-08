"""
Tests for JustNews Fact Checker Agent
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from agents.fact_checker.tools import (
    assess_credibility,
    comprehensive_fact_check,
    detect_contradictions,
    extract_claims,
    get_fact_checker_engine,
    process_fact_check_request,
    validate_sources,
    verify_facts,
)


class TestFactCheckerTools:
    """Test fact checker agent tools"""

    def test_get_fact_checker_engine_singleton(self):
        """Test that get_fact_checker_engine returns singleton instance"""
        with patch("agents.fact_checker.tools.FactCheckerEngine") as mock_engine_class:
            mock_engine = Mock()
            mock_engine_class.return_value = mock_engine

            # Reset global engine
            import agents.fact_checker.tools

            agents.fact_checker.tools._engine = None

            engine1 = get_fact_checker_engine()
            engine2 = get_fact_checker_engine()

            assert engine1 is engine2
            assert engine1 is mock_engine
            mock_engine_class.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_fact_check_request_verify_facts(self):
        """Test processing fact verification request"""
        mock_engine = Mock()
        mock_engine.verify_facts.return_value = {
            "verdict": "true",
            "confidence": 0.85,
            "evidence": ["Source confirms claim"],
            "contradictions": [],
        }

        with patch(
            "agents.fact_checker.tools.get_fact_checker_engine",
            return_value=mock_engine,
        ):
            result = await process_fact_check_request(
                content="The Earth is round.", operation_type="verify_facts"
            )

            assert result["verdict"] == "true"
            assert result["confidence"] == 0.85
            assert len(result["evidence"]) == 1
            mock_engine.verify_facts.assert_called_once_with("The Earth is round.")

    @pytest.mark.asyncio
    async def test_process_fact_check_request_validate_sources(self):
        """Test processing source validation request"""
        mock_engine = Mock()
        mock_engine.validate_sources.return_value = {
            "overall_credibility": 0.75,
            "sources": [
                {"url": "example.com", "credibility_score": 0.8},
                {"url": "news.org", "credibility_score": 0.9},
            ],
        }

        with patch(
            "agents.fact_checker.tools.get_fact_checker_engine",
            return_value=mock_engine,
        ):
            result = await process_fact_check_request(
                content="Article content here",
                operation_type="validate_sources",
                sources=["example.com", "news.org"],
            )

            assert result["overall_credibility"] == 0.75
            assert len(result["sources"]) == 2
            mock_engine.validate_sources.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_fact_check_request_unknown_type(self):
        """Test processing request with unknown operation type"""
        mock_engine = Mock()

        with patch(
            "agents.fact_checker.tools.get_fact_checker_engine",
            return_value=mock_engine,
        ):
            result = await process_fact_check_request(
                content="Sample content", operation_type="unknown"
            )

            assert result["error"] == "Unknown operation type: unknown"
            assert "supported_types" in result

    @pytest.mark.asyncio
    async def test_process_fact_check_request_engine_error(self):
        """Test handling engine errors"""
        mock_engine = Mock()
        mock_engine.verify_facts.side_effect = Exception("Engine failure")

        with patch(
            "agents.fact_checker.tools.get_fact_checker_engine",
            return_value=mock_engine,
        ):
            result = await process_fact_check_request(
                content="Test content", operation_type="verify_facts"
            )

            assert result["error"] == "Engine failure"
            assert "Engine failure" in result["details"]

    def test_verify_facts_wrapper(self):
        """Test verify_facts wrapper function"""
        with patch(
            "agents.fact_checker.tools.process_fact_check_request"
        ) as mock_process:
            mock_process.return_value = {
                "verdict": "partially_true",
                "confidence": 0.7,
                "evidence": ["Some supporting evidence"],
            }

            result = verify_facts("Climate change is real.")

            assert result["verdict"] == "partially_true"
            assert result["confidence"] == 0.7
            mock_process.assert_called_once()

    def test_validate_sources_wrapper(self):
        """Test validate_sources wrapper function"""
        with patch(
            "agents.fact_checker.tools.process_fact_check_request"
        ) as mock_process:
            mock_process.return_value = {
                "overall_credibility": 0.6,
                "sources": [{"url": "example.com", "score": 0.6}],
            }

            sources = ["example.com", "news.org"]
            result = validate_sources("Article content", sources)

            assert result["overall_credibility"] == 0.6
            mock_process.assert_called_once_with(
                content="Article content",
                operation_type="validate_sources",
                sources=sources,
            )

    def test_comprehensive_fact_check_wrapper(self):
        """Test comprehensive_fact_check wrapper function"""
        with patch(
            "agents.fact_checker.tools.process_fact_check_request"
        ) as mock_process:
            mock_process.return_value = {
                "overall_verdict": "true",
                "claim_checks": [
                    {"claim": "Fact 1", "verdict": "true"},
                    {"claim": "Fact 2", "verdict": "false"},
                ],
                "source_credibility": 0.8,
            }

            result = comprehensive_fact_check("Full article text")

            assert result["overall_verdict"] == "true"
            assert len(result["claim_checks"]) == 2
            mock_process.assert_called_once()

    def test_extract_claims_wrapper(self):
        """Test extract_claims wrapper function"""
        with patch(
            "agents.fact_checker.tools.process_fact_check_request"
        ) as mock_process:
            mock_process.return_value = {
                "claims": [
                    "The sky is blue",
                    "Water boils at 100°C",
                    "Humans need oxygen to survive",
                ]
            }

            result = extract_claims("Article with multiple claims.")

            assert len(result) == 3
            assert "sky is blue" in result[0]
            mock_process.assert_called_once()

    def test_assess_credibility_wrapper(self):
        """Test assess_credibility wrapper function"""
        with patch(
            "agents.fact_checker.tools.process_fact_check_request"
        ) as mock_process:
            mock_process.return_value = {
                "credibility_score": 0.75,
                "factors": ["Domain authority", "Content quality"],
                "recommendations": ["Generally reliable"],
            }

            result = assess_credibility("newswebsite.com")

            assert result["credibility_score"] == 0.75
            assert len(result["factors"]) == 2
            mock_process.assert_called_once()

    def test_detect_contradictions_wrapper(self):
        """Test detect_contradictions wrapper function"""
        with patch(
            "agents.fact_checker.tools.process_fact_check_request"
        ) as mock_process:
            mock_process.return_value = {
                "contradictions": [
                    {
                        "text": "Statement A contradicts Statement B",
                        "severity": "high",
                        "explanation": "Direct contradiction",
                    }
                ],
                "logical_consistency": 0.3,
            }

            text = "The article makes contradictory claims."
            result = detect_contradictions(text)

            assert len(result["contradictions"]) == 1
            assert result["contradictions"][0]["severity"] == "high"
            mock_process.assert_called_once()


class TestFactCheckerMainApp:
    """Test fact checker agent FastAPI application"""

    def test_app_creation(self):
        """Test that the FastAPI app can be created"""
        with (
            patch("agents.fact_checker.main.JustNewsMetrics"),
            patch("agents.fact_checker.main.create_database_service"),
            patch("agents.fact_checker.main.get_logger"),
        ):
            from agents.fact_checker.main import app

            assert app is not None
            assert hasattr(app, "routes")

    @patch("agents.fact_checker.main.validate_content_size")
    @patch("agents.fact_checker.main.sanitize_content")
    @patch("agents.fact_checker.main.verify_facts")
    def test_verify_endpoint(self, mock_verify, mock_sanitize, mock_validate):
        """Test the /verify endpoint"""
        mock_validate.return_value = True
        mock_sanitize.return_value = "sanitized content"
        mock_verify.return_value = {
            "verdict": "true",
            "confidence": 0.9,
            "evidence": ["Reliable source confirms"],
        }

        with (
            patch("agents.fact_checker.main.JustNewsMetrics"),
            patch("agents.fact_checker.main.create_database_service"),
            patch("agents.fact_checker.main.get_logger"),
        ):
            from agents.fact_checker.main import app

            client = TestClient(app)

            response = client.post(
                "/verify", json={"content": "The Earth orbits the Sun."}
            )

            assert response.status_code == 200
            data = response.json()
            assert data["verdict"] == "true"
            assert data["confidence"] == 0.9

    @patch("agents.fact_checker.main.validate_content_size")
    def test_verify_endpoint_content_too_large(self, mock_validate):
        """Test handling of oversized content"""
        mock_validate.return_value = False

        with (
            patch("agents.fact_checker.main.JustNewsMetrics"),
            patch("agents.fact_checker.main.create_database_service"),
            patch("agents.fact_checker.main.get_logger"),
        ):
            from agents.fact_checker.main import app

            client = TestClient(app)

            large_content = "x" * 2000000  # 2MB content
            response = client.post("/verify", json={"content": large_content})

            assert response.status_code == 400
            assert "Content too large" in response.json()["detail"]

    @patch("agents.fact_checker.main.extract_claims")
    def test_extract_claims_endpoint(self, mock_extract):
        """Test the /extract-claims endpoint"""
        mock_extract.return_value = [
            "Claim 1: The sky is blue",
            "Claim 2: Water is wet",
        ]

        with (
            patch("agents.fact_checker.main.JustNewsMetrics"),
            patch("agents.fact_checker.main.create_database_service"),
            patch("agents.fact_checker.main.get_logger"),
            patch("agents.fact_checker.main.validate_content_size", return_value=True),
            patch(
                "agents.fact_checker.main.sanitize_content", return_value="sanitized"
            ),
        ):
            from agents.fact_checker.main import app

            client = TestClient(app)

            response = client.post(
                "/extract-claims", json={"content": "The sky is blue. Water is wet."}
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert "sky is blue" in data[0]

    def test_health_endpoint(self):
        """Test the /health endpoint"""
        with (
            patch("agents.fact_checker.main.JustNewsMetrics"),
            patch("agents.fact_checker.main.create_database_service"),
            patch("agents.fact_checker.main.get_logger"),
        ):
            from agents.fact_checker.main import app

            client = TestClient(app)

            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "fact_checker" in data["service"]

    def test_metrics_endpoint(self):
        """Test the /metrics endpoint"""
        with (
            patch("agents.fact_checker.main.JustNewsMetrics") as mock_metrics_class,
            patch("agents.fact_checker.main.create_database_service"),
            patch("agents.fact_checker.main.get_logger"),
        ):
            mock_metrics = Mock()
            mock_metrics.get_metrics.return_value = "# Fact checker metrics"
            mock_metrics_class.return_value = mock_metrics

            from agents.fact_checker.main import app

            client = TestClient(app)

            response = client.get("/metrics")

            assert response.status_code == 200
            assert "# Fact checker metrics" in response.text
