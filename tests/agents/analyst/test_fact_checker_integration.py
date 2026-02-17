"""
Integration tests for Analyst + Fact-Checker integration.

Tests the mandatory per-article fact-checking feature as specified in
docs/feat_article_creation.md.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def fake_engine():
    """Provide a real AnalystEngine instance for integration tests."""
    from agents.analyst.analyst_engine import AnalystEngine

    return AnalystEngine()


@pytest.fixture
def mock_fact_checker():
    """Mock modern async audit_text integration path."""
    with patch("agents.analyst.audit.audit_text", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "score": 0.85,
            "details": {
                "checked_count": 2,
                "verdict_breakdown": {"Likely True": 2},
            },
            "verdicts": [
                {
                    "claim": "Test claim 1",
                    "confidence": 0.9,
                    "fact_check": {"verdict": "Likely True", "confidence": 0.9},
                },
                {
                    "claim": "Test claim 2",
                    "confidence": 0.85,
                    "fact_check": {"verdict": "Likely True", "confidence": 0.85},
                },
            ],
        }
        yield mock


class TestFactCheckerIntegration:
    """Test Analyst integration with Fact-Checker."""

    def test_generate_analysis_report_calls_fact_checker(
        self, fake_engine, mock_fact_checker
    ):
        """Test that generate_analysis_report calls fact-checker for each article."""
        texts = ["Article 1 text", "Article 2 text"]
        article_ids = ["art1", "art2"]

        _report = fake_engine.generate_analysis_report(
            texts=texts,
            article_ids=article_ids,
            cluster_id="test_cluster",
            enable_fact_check=True,
        )

        # Verify fact-checker was called for each article
        assert mock_fact_checker.call_count == 2

        # Verify call arguments
        first_call = mock_fact_checker.call_args_list[0]
        assert first_call.args[0] == "Article 1 text"
        assert first_call.kwargs["max_claims"] == 5

        second_call = mock_fact_checker.call_args_list[1]
        assert second_call.args[0] == "Article 2 text"
        assert second_call.kwargs["max_claims"] == 5

    def test_generate_analysis_report_attaches_source_fact_checks(
        self, fake_engine, mock_fact_checker
    ):
        """Test that source_fact_checks are attached to AnalysisReport."""
        texts = ["Article text"]
        article_ids = ["art1"]

        report = fake_engine.generate_analysis_report(
            texts=texts, article_ids=article_ids, enable_fact_check=True
        )

        # Verify source_fact_checks field exists
        assert "source_fact_checks" in report
        assert len(report["source_fact_checks"]) == 1

        sfc = report["source_fact_checks"][0]
        assert sfc["article_id"] == "art1"
        assert sfc["fact_check_status"] == "passed"  # overall_score=0.85 >= 0.8
        assert sfc["overall_score"] == 0.85
        assert sfc["credibility_score"] == 0.85

    def test_generate_analysis_report_per_article_includes_fact_check(
        self, fake_engine, mock_fact_checker
    ):
        """Test that per_article results include source_fact_check."""
        texts = ["Article text"]
        article_ids = ["art1"]

        report = fake_engine.generate_analysis_report(
            texts=texts, article_ids=article_ids, enable_fact_check=True
        )

        per_article = report["per_article"][0]
        assert per_article["source_fact_check"] is not None
        assert per_article["source_fact_check"]["article_id"] == "art1"
        assert per_article["source_fact_check"]["fact_check_status"] == "passed"

    def test_generate_analysis_report_cluster_summary(
        self, fake_engine, mock_fact_checker
    ):
        """Test cluster_fact_check_summary aggregation."""
        # Mock different fact-check statuses
        mock_fact_checker.side_effect = [
            {
                "score": 0.85,
                "details": {"checked_count": 0, "verdict_breakdown": {}},
                "verdicts": [],
            },
            {
                "score": 0.65,
                "details": {"checked_count": 0, "verdict_breakdown": {}},
                "verdicts": [],
            },
            {
                "score": 0.45,
                "details": {"checked_count": 0, "verdict_breakdown": {}},
                "verdicts": [],
            },
        ]

        texts = ["Article 1", "Article 2", "Article 3"]
        article_ids = ["art1", "art2", "art3"]

        report = fake_engine.generate_analysis_report(
            texts=texts,
            article_ids=article_ids,
            cluster_id="test_cluster",
            enable_fact_check=True,
        )

        summary = report["cluster_fact_check_summary"]
        assert summary["total_articles_checked"] == 3
        assert summary["passed_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["needs_review_count"] == 1
        assert summary["average_overall_score"] == pytest.approx(
            (0.85 + 0.65 + 0.45) / 3, rel=1e-3
        )
        assert summary["articles_flagged"] == ["art3"]
        assert summary["percent_verified"] == pytest.approx(100.0 / 3, rel=1e-2)

    def test_fact_check_status_thresholds(self, fake_engine, mock_fact_checker):
        """Test fact_check_status is correctly determined by overall_score."""
        test_cases = [
            (0.95, "passed"),
            (0.80, "passed"),
            (0.75, "needs_review"),
            (0.60, "needs_review"),
            (0.55, "failed"),
            (0.20, "failed"),
        ]

        for score, expected_status in test_cases:
            mock_fact_checker.reset_mock()
            mock_fact_checker.return_value = {
                "score": score,
                "details": {"checked_count": 0, "verdict_breakdown": {}},
                "verdicts": [],
            }

            report = fake_engine.generate_analysis_report(
                texts=["Test text"], article_ids=["test"], enable_fact_check=True
            )

            sfc = report["source_fact_checks"][0]
            assert sfc["fact_check_status"] == expected_status, (
                f"Score {score} should map to status {expected_status}"
            )

    def test_generate_analysis_report_disable_fact_check(
        self, fake_engine, mock_fact_checker
    ):
        """Test that fact-checking can be disabled with enable_fact_check=False."""
        report = fake_engine.generate_analysis_report(
            texts=["Article text"], article_ids=["art1"], enable_fact_check=False
        )

        # Verify fact-checker was not called
        assert mock_fact_checker.call_count == 0

        # Verify no source_fact_checks
        assert report["source_fact_checks"] == []
        assert report["cluster_fact_check_summary"] is None

        # Verify per_article has no source_fact_check
        per_article = report["per_article"][0]
        assert per_article["source_fact_check"] is None

    def test_fact_checker_import_error_handling(self, fake_engine, caplog):
        """Test graceful handling when fact-checker is not available."""
        with patch(
            "agents.analyst.audit.audit_text",
            new_callable=AsyncMock,
            side_effect=ImportError("No module named 'agents.fact_checker'"),
        ):
            report = fake_engine.generate_analysis_report(
                texts=["Article text"], article_ids=["art1"], enable_fact_check=True
            )

            # Should not crash, just log error
            assert (
                "Per-article fact-check failed for art1" in caplog.text
                or "Fact-checker is not available" in caplog.text
            )
            assert report["source_fact_checks"] == []

    def test_fact_checker_error_response_handling(
        self, fake_engine, mock_fact_checker, caplog
    ):
        """Test handling of fact-checker error responses."""
        mock_fact_checker.return_value = {"error": "Fact-check service unavailable"}

        report = fake_engine.generate_analysis_report(
            texts=["Article text"], article_ids=["art1"], enable_fact_check=True
        )

        # Should log error and continue
        assert "Fact-check failed for article" in caplog.text
        assert len(report["source_fact_checks"]) == 0

    def test_claim_verdicts_extraction(self, fake_engine, mock_fact_checker):
        """Test that claim_verdicts are correctly extracted from fact-checker response."""
        mock_fact_checker.return_value = {
            "score": 0.80,
            "details": {"checked_count": 3, "verdict_breakdown": {"Likely True": 2, "False": 1}},
            "verdicts": [
                {
                    "claim": "Claim 1",
                    "confidence": 0.95,
                    "fact_check": {
                        "verdict": "Likely True",
                        "confidence": 0.95,
                        "evidence": [{"source": "test"}],
                    },
                },
                {
                    "claim": "Claim 2",
                    "confidence": 0.70,
                    "fact_check": {
                        "verdict": "Uncertain",
                        "confidence": 0.70,
                        "evidence": None,
                    },
                },
                {
                    "claim": "Claim 3",
                    "confidence": 0.85,
                    "fact_check": {
                        "verdict": "False",
                        "confidence": 0.85,
                        "evidence": [],
                    },
                },
            ],
        }

        report = fake_engine.generate_analysis_report(
            texts=["Article text"], article_ids=["art1"], enable_fact_check=True
        )

        sfc = report["source_fact_checks"][0]
        claim_verdicts = sfc["claim_verdicts"]

        assert len(claim_verdicts) == 3
        assert claim_verdicts[0]["claim_text"] == "Claim 1"
        assert claim_verdicts[0]["verdict"] == "Likely True"
        assert claim_verdicts[0]["confidence"] == 0.95
        assert claim_verdicts[0]["evidence"] == [{"source": "test"}]

        assert claim_verdicts[1]["claim_text"] == "Claim 2"
        assert claim_verdicts[1]["verdict"] == "Uncertain"
        assert claim_verdicts[1]["confidence"] == 0.70

    def test_fact_check_trace_includes_full_details(
        self, fake_engine, mock_fact_checker
    ):
        """Test that fact_check_trace captures comprehensive details."""
        mock_fact_checker.return_value = {
            "score": 0.75,
            "details": {
                "checked_count": 5,
                "verdict_breakdown": {"Likely True": 4, "Uncertain": 1},
            },
            "verdicts": [],
        }

        report = fake_engine.generate_analysis_report(
            texts=["Article text"], article_ids=["art1"], enable_fact_check=True
        )

        sfc = report["source_fact_checks"][0]
        trace = sfc["fact_check_trace"]

        assert trace["fact_verification"]["verification_score"] == 0.75
        assert trace["credibility_assessment"]["credibility_score"] == 0.75
        assert trace["claims_analyzed"] == 5
        assert trace["contradictions"] == {}

    def test_empty_texts_list(self, fake_engine, mock_fact_checker):
        """Test handling of empty texts list."""
        report = fake_engine.generate_analysis_report(
            texts=[], article_ids=[], enable_fact_check=True
        )

        assert mock_fact_checker.call_count == 0
        assert report["source_fact_checks"] == []
        assert report["cluster_fact_check_summary"] is None
        assert report["articles_count"] == 0

    def test_multiple_articles_fact_check_isolation(
        self, fake_engine, mock_fact_checker
    ):
        """Test that each article gets independent fact-check call."""
        # Set up different responses for each article
        responses = [
            {
                "score": 0.90,
                "details": {"checked_count": 0, "verdict_breakdown": {}},
                "verdicts": [],
            },
            {
                "score": 0.50,
                "details": {"checked_count": 0, "verdict_breakdown": {}},
                "verdicts": [],
            },
        ]
        mock_fact_checker.side_effect = responses

        report = fake_engine.generate_analysis_report(
            texts=["Article 1", "Article 2"],
            article_ids=["art1", "art2"],
            enable_fact_check=True,
        )

        # Verify independent results
        assert len(report["source_fact_checks"]) == 2
        assert report["source_fact_checks"][0]["overall_score"] == 0.90
        assert report["source_fact_checks"][0]["fact_check_status"] == "passed"
        assert report["source_fact_checks"][1]["overall_score"] == 0.50
        assert report["source_fact_checks"][1]["fact_check_status"] == "failed"
