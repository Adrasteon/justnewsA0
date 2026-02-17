"""
Tests for AnalystEngine - Core Quantitative Analysis Engine

Comprehensive tests for the AnalystEngine class covering:
- Entity extraction with spaCy and transformer fallbacks
- Text statistics and readability analysis
- GPU-accelerated sentiment and bias analysis
- Key metrics extraction (financial, temporal, statistical)
- Content trend analysis across multiple articles
- Error handling and edge cases
"""

import sys
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

# Add agents to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "agents"))

# Mock the module-level imports before importing AnalystEngine
import importlib.util

original_find_spec = importlib.util.find_spec


def mock_find_spec(name, package=None):
    # Return None for all dependencies to simulate them not being available
    return None


importlib.util.find_spec = mock_find_spec

from analyst.analyst_engine import AnalystConfig, AnalystEngine  # noqa: E402


class TestAnalystEngineInitialization:
    """Test AnalystEngine initialization and configuration"""

    def test_init_default_config(self):
        """Test initialization with default configuration"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()
            assert isinstance(engine, AnalystEngine)
            assert isinstance(engine.config, AnalystConfig)
            assert engine.processing_stats is not None

    def test_init_custom_config(self):
        """Test initialization with custom configuration"""
        custom_config = AnalystConfig()
        custom_config.max_text_length = 5000
        custom_config.use_gpu = False

        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
        ):
            engine = AnalystEngine(config=custom_config)

            assert engine.config is custom_config
            assert engine.config.max_text_length == 5000
            assert engine.config.use_gpu is False

    @patch("agents.analyst.analyst_engine._import_spacy")
    def test_init_spacy_failure(self, mock_import_spacy):
        """Test spaCy initialization failure fallback"""
        mock_import_spacy.return_value = None

        with (
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            assert engine.spacy_nlp is None

    def test_context_manager(self):
        """Test context manager functionality"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
            patch.object(AnalystEngine, "_cleanup_resources") as mock_cleanup,
        ):
            with AnalystEngine() as engine:
                assert isinstance(engine, AnalystEngine)

            mock_cleanup.assert_called_once()


class TestTextValidation:
    """Test text input validation"""

    def test_validate_text_input_valid(self):
        """Test validation of valid text input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            assert engine._validate_text_input("Valid text content")
            assert engine._validate_text_input("A")

    def test_validate_text_input_invalid(self):
        """Test validation of invalid text input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            assert not engine._validate_text_input("")
            assert not engine._validate_text_input("   ")
            assert not engine._validate_text_input(None)

    def test_validate_text_input_too_long(self):
        """Test validation of text that exceeds maximum length"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()
            long_text = "A" * (engine.config.max_text_length + 1)

            assert not engine._validate_text_input(long_text)


class TestEntityExtraction:
    """Test entity extraction functionality"""

    def test_extract_entities_spacy_success(self):
        """Test entity extraction using spaCy"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            # Mock spaCy
            mock_doc = Mock()
            mock_ent1 = Mock()
            mock_ent1.text = "Apple"
            mock_ent1.label_ = "ORG"
            mock_ent1.start_char = 0
            mock_ent1.end_char = 5
            mock_ent2 = Mock()
            mock_ent2.text = "John Smith"
            mock_ent2.label_ = "PERSON"
            mock_ent2.start_char = 10
            mock_ent2.end_char = 20

            mock_doc.ents = [mock_ent1, mock_ent2]
            engine.spacy_nlp = Mock(return_value=mock_doc)

            result = engine.extract_entities("Apple announced that John Smith joined.")

            assert result["total_entities"] == 2
            assert result["method"] == "spacy"
            assert len(result["entities"]) == 2
            assert result["entities"][0]["text"] == "Apple"
            assert result["entities"][0]["label"] == "ORG"

    def test_extract_entities_transformer_fallback(self):
        """Test entity extraction using transformer fallback"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            # Mock transformer pipeline
            mock_pipeline = Mock()
            mock_pipeline.return_value = [
                {
                    "word": "Apple",
                    "entity_group": "ORG",
                    "start": 0,
                    "end": 5,
                    "score": 0.95,
                },
                {
                    "word": "John Smith",
                    "entity_group": "PERSON",
                    "start": 10,
                    "end": 20,
                    "score": 0.88,
                },
            ]
            engine.ner_pipeline = mock_pipeline

            result = engine.extract_entities("Apple announced that John Smith joined.")

            assert result["total_entities"] == 2
            assert result["method"] == "transformer"
            assert len(result["entities"]) == 2

    def test_extract_entities_pattern_fallback(self):
        """Test entity extraction using pattern fallback"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.extract_entities(
                "Apple announced that John Smith joined the company."
            )

            assert result["total_entities"] >= 1
            assert result["method"] == "patterns"
            assert "entities" in result

    def test_extract_entities_invalid_input(self):
        """Test entity extraction with invalid input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.extract_entities("")

            assert result["total_entities"] == 0
            assert "error" in result

    def test_extract_entities_error_handling(self):
        """Test entity extraction error handling"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            # Mock spaCy to raise exception
            engine.spacy_nlp = Mock(side_effect=Exception("spaCy error"))

            result = engine.extract_entities("Test text")

            assert result["total_entities"] == 0
            assert result["method"] == "error"
            assert "error" in result


class TestTextStatisticsAnalysis:
    """Test text statistics analysis functionality"""

    def test_analyze_text_statistics_basic(self):
        """Test basic text statistics analysis"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            text = "This is a test sentence. It contains multiple words and should be analyzed properly."
            result = engine.analyze_text_statistics(text)

            assert "word_count" in result
            assert "sentence_count" in result
            assert "character_count" in result
            assert "readability_score" in result
            assert result["word_count"] > 0
            assert result["sentence_count"] > 0

    def test_analyze_text_statistics_complexity(self):
        """Test text complexity analysis"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            text = "This is a sophisticated sentence containing numerous polysyllabic words that significantly increase the complexity of the textual content being analyzed."
            result = engine.analyze_text_statistics(text)

            assert "complex_words" in result
            assert "complex_word_ratio" in result
            assert "vocabulary_diversity" in result
            assert result["complex_words"] > 0

    def test_analyze_text_statistics_numbers(self):
        """Test number extraction in text statistics"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            text = "The company reported $1.5 million in revenue and 25% growth."
            result = engine.analyze_text_statistics(text)

            assert "numbers_found" in result
            assert "numeric_density" in result
            assert result["numbers_found"] >= 2

    def test_analyze_text_statistics_invalid_input(self):
        """Test text statistics with invalid input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.analyze_text_statistics("")

            assert "error" in result


class TestKeyMetricsExtraction:
    """Test key metrics extraction functionality"""

    def test_extract_key_metrics_financial(self):
        """Test financial metrics extraction"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            text = (
                "The company reported $2.5 billion in revenue, up 15% from last year."
            )
            result = engine.extract_key_metrics(text)

            assert "metrics" in result
            assert "total_metrics" in result
            assert result["total_metrics"] > 0

            # Check for financial metrics
            financial_metrics = [
                m for m in result["metrics"] if m.get("type") == "currency"
            ]
            assert len(financial_metrics) > 0

    def test_extract_key_metrics_temporal(self):
        """Test temporal metrics extraction"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            text = (
                "The event happened on January 15, 2024, and will continue next week."
            )
            result = engine.extract_key_metrics(text)

            assert "metrics" in result
            assert result["total_metrics"] > 0

    def test_extract_key_metrics_invalid_input(self):
        """Test key metrics extraction with invalid input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.extract_key_metrics("")

            assert result["total_metrics"] == 0
            assert "error" in result


class TestSentimentAnalysis:
    """Test sentiment analysis functionality"""

    def test_analyze_sentiment_gpu_success(self):
        """Test sentiment analysis with GPU acceleration"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
        ):
            engine = AnalystEngine()

            # Mock GPU analyst
            mock_gpu = Mock()
            mock_gpu.score_sentiment_gpu.return_value = 0.8
            engine.gpu_analyst = mock_gpu

            result = engine.analyze_sentiment("This is a great product!")

            assert result["dominant_sentiment"] == "positive"
            assert result["confidence"] > 0.5
            assert result["method"] == "gpu_accelerated"
            assert "sentiment_scores" in result

    def test_analyze_sentiment_heuristic_fallback(self):
        """Test sentiment analysis with heuristic fallback"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.analyze_sentiment("This product is amazing and wonderful!")

            assert result["dominant_sentiment"] == "positive"
            assert result["method"] == "heuristic_keywords"
            assert "sentiment_scores" in result

    def test_analyze_sentiment_neutral(self):
        """Test neutral sentiment analysis"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.analyze_sentiment(
                "The product exists and functions as expected."
            )

            assert result["dominant_sentiment"] == "neutral"
            assert result["method"] == "heuristic_keywords"

    def test_analyze_sentiment_invalid_input(self):
        """Test sentiment analysis with invalid input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.analyze_sentiment("")

            assert "error" in result


class TestBiasDetection:
    """Test bias detection functionality"""

    def test_detect_bias_gpu_success(self):
        """Test bias detection with GPU acceleration"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
        ):
            engine = AnalystEngine()

            # Mock GPU analyst
            mock_gpu = Mock()
            mock_gpu.score_bias_gpu.return_value = 0.8
            engine.gpu_analyst = mock_gpu

            result = engine.detect_bias(
                "This opinion is absolutely the best and only correct view!"
            )

            assert result["has_bias"] is True
            assert result["bias_level"] == "high"
            assert result["method"] == "gpu_accelerated"
            assert "bias_score" in result

    def test_detect_bias_heuristic_fallback(self):
        """Test bias detection with heuristic fallback"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.detect_bias(
                "Liberals are always wrong and conservatives are always right!"
            )

            assert result["has_bias"] is True
            assert result["bias_level"] in ["high", "medium"]
            assert result["method"] == "heuristic_keywords"

    def test_detect_bias_low_bias(self):
        """Test low bias detection"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.detect_bias(
                "The facts show that the data supports this conclusion."
            )

            assert result["bias_level"] in ["low", "minimal"]
            assert result["method"] == "heuristic_keywords"


class TestContentTrendsAnalysis:
    """Test content trends analysis functionality"""

    def test_analyze_content_trends_with_spacy(self):
        """Test content trends analysis with spaCy available"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            # Mock spaCy for entity analysis
            mock_doc1 = Mock()
            mock_ent1 = Mock()
            mock_ent1.text = "Apple"
            mock_ent1.label_ = "ORG"
            mock_doc1.ents = [mock_ent1]

            mock_doc2 = Mock()
            mock_ent2 = Mock()
            mock_ent2.text = "Apple"
            mock_ent2.label_ = "ORG"
            mock_doc2.ents = [mock_ent2]

            engine.spacy_nlp = Mock(side_effect=[mock_doc1, mock_doc2])

            texts = ["Apple announced new products.", "Apple is expanding globally."]
            result = engine.analyze_content_trends(texts)

            assert "trends" in result
            assert "topics" in result
            assert result["total_texts"] == 2
            assert len(result["trends"]) > 0

    def test_analyze_content_trends_topic_analysis(self):
        """Test topic trend analysis"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            texts = [
                "Technology is advancing rapidly.",
                "New technology changes everything.",
            ]
            result = engine.analyze_content_trends(texts)

            assert "topics" in result
            assert len(result["topics"]) > 0
            assert result["topics"][0]["topic"] == "technology"

    def test_analyze_content_trends_empty_input(self):
        """Test content trends with empty input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.analyze_content_trends([])

            assert "error" in result
            assert "total_texts" not in result


class TestCombinedAnalysis:
    """Test combined sentiment and bias analysis"""

    def test_analyze_sentiment_and_bias_combined(self):
        """Test combined sentiment and bias analysis"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.analyze_sentiment_and_bias(
                "This is a balanced and factual article."
            )

            assert "sentiment_analysis" in result
            assert "bias_analysis" in result
            assert "combined_assessment" in result
            assert "overall_reliability" in result["combined_assessment"]
            assert "content_quality_score" in result["combined_assessment"]
            assert "recommendations" in result["combined_assessment"]

    def test_analyze_sentiment_and_bias_invalid_input(self):
        """Test combined analysis with invalid input"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            result = engine.analyze_sentiment_and_bias("")

            assert "error" in result


class TestErrorHandling:
    """Test error handling across all methods"""

    def test_method_error_handling(self):
        """Test that all methods handle exceptions gracefully"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            # Test various methods with invalid inputs or forced errors
            methods_to_test = [
                ("extract_entities", [""]),
                ("analyze_text_statistics", [""]),
                ("extract_key_metrics", [""]),
                ("analyze_sentiment", [""]),
                ("detect_bias", [""]),
                ("analyze_sentiment_and_bias", [""]),
                ("analyze_content_trends", [[]]),
            ]

            for method_name, args in methods_to_test:
                method = getattr(engine, method_name)
                result = method(*args)

                # All methods should return a dict with either results or error
                assert isinstance(result, dict)
                assert "error" in result or len(result) > 0


class TestProcessingStats:
    """Test processing statistics tracking"""

    def test_processing_stats_tracking(self):
        """Test that processing statistics are properly tracked"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            initial_processed = engine.processing_stats["total_processed"]

            # Perform some operations
            engine.extract_entities("Test text for entity extraction.")
            engine.analyze_text_statistics("Test text for statistics.")
            engine.analyze_sentiment("Test text for sentiment.")
            engine.detect_bias("Test text for bias.")

            # Check that stats were updated
            assert engine.processing_stats["total_processed"] > initial_processed
            assert engine.processing_stats["entities_extracted"] >= 0
            assert engine.processing_stats["sentiment_analyses"] >= 0
            assert engine.processing_stats["bias_detections"] >= 0


class TestFeedbackLogging:
    """Test feedback logging functionality"""

    def test_feedback_logging(self):
        """Test that feedback is logged correctly"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
            patch("builtins.open", mock_open()) as mock_file,
        ):
            engine = AnalystEngine()

            # Perform an operation that should log feedback
            engine.extract_entities("Test text")

            # Check that feedback was logged
            mock_file.assert_called()
            # The exact call verification would depend on the implementation details


# Integration tests combining multiple components
class TestAnalystEngineIntegration:
    """Integration tests for AnalystEngine combining multiple components"""

    def test_full_analysis_pipeline(self):
        """Test complete analysis pipeline from text to insights"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            article_text = """
            Apple Inc. reported $94.5 billion in quarterly revenue, representing a 15% increase
            from the previous year. The technology giant announced new products including the
            iPhone 15 and MacBook Pro. CEO Tim Cook stated that the company is optimistic
            about future growth despite economic challenges.
            """

            # Extract entities
            entities = engine.extract_entities(article_text)
            assert entities["total_entities"] > 0

            # Analyze statistics
            stats = engine.analyze_text_statistics(article_text)
            assert stats["word_count"] > 10
            assert stats["numbers_found"] > 0

            # Extract key metrics
            metrics = engine.extract_key_metrics(article_text)
            assert metrics["total_metrics"] > 0

            # Analyze sentiment
            sentiment = engine.analyze_sentiment(article_text)
            assert "dominant_sentiment" in sentiment

            # Detect bias
            bias = engine.detect_bias(article_text)
            assert "bias_level" in bias

            # Combined analysis
            combined = engine.analyze_sentiment_and_bias(article_text)
            assert "combined_assessment" in combined

    def test_multiple_articles_trend_analysis(self):
        """Test trend analysis across multiple articles"""
        with (
            patch(
                "agents.analyst.analyst_engine._import_spacy", return_value=(None, None)
            ),
            patch(
                "agents.analyst.analyst_engine._import_transformers_pipeline",
                return_value=(None, None),
            ),
            patch(
                "agents.analyst.analyst_engine.AnalystEngine._initialize_gpu_analyst"
            ),
        ):
            engine = AnalystEngine()

            articles = [
                "Apple announces new iPhone with advanced features.",
                "Apple's stock rises after strong quarterly earnings report.",
                "Apple expands operations in Asia with new manufacturing facilities.",
                "Apple faces criticism over labor practices in supply chain.",
            ]

            trends = engine.analyze_content_trends(articles)

            assert trends["total_texts"] == 4
            assert len(trends["trends"]) > 0
            assert len(trends["topics"]) > 0
