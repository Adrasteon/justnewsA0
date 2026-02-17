"""Comprehensive unit tests for the SynthesizerEngine class."""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
import torch

from agents.synthesizer.synthesizer_engine import SynthesizerEngine


class StubGPUManager:
    """Stub GPU manager for testing."""

    def __init__(self):
        self.is_available = True
        self.device = "cuda:0"

    def get_device(self):
        return self.device

    def get_available_memory(self):
        return 8 * 1024 * 1024 * 1024  # 8GB


class StubModel:
    """Stub ML model for testing."""

    def __init__(self):
        self.device = "cpu"

    def to(self, device):
        self.device = device
        return self

    def generate(self, **kwargs):
        return torch.tensor([[1, 2, 3, 4, 5]])  # Mock generated tokens


class StubTokenizer:
    """Stub tokenizer for testing."""

    def __init__(self):
        self.pad_token_id = 0

    def __call__(self, text, **kwargs):
        return {
            "input_ids": torch.tensor([[1, 2, 3]]),
            "attention_mask": torch.tensor([[1, 1, 1]]),
        }

    def decode(self, tokens, **kwargs):
        return "Mock decoded text"

    def batch_decode(self, tokens, **kwargs):
        return ["Mock decoded text"]


class StubBERTopicModel:
    """Stub BERTopic model for testing."""

    def __init__(self):
        self.topics = [0, 1, 2]
        self.probs = [[0.8, 0.15, 0.05]]

    def fit_transform(self, documents):
        return self.topics, self.probs

    def get_topic_info(self):
        return [
            {"Topic": 0, "Count": 10, "Name": "Topic 0"},
            {"Topic": 1, "Count": 5, "Name": "Topic 1"},
        ]


@pytest.fixture(autouse=True)
def gpu_manager_stub(monkeypatch):
    """Stub the GPU manager module."""
    monkeypatch.setitem(
        sys.modules, "common.gpu_utils", SimpleNamespace(GPUManager=StubGPUManager)
    )
    yield
    sys.modules.pop("common.gpu_utils", None)


@pytest_asyncio.fixture
async def mock_gpu_manager():
    """Create a mock GPU manager."""
    manager = StubGPUManager()
    return manager


@pytest_asyncio.fixture
async def synthesizer_engine(mock_gpu_manager):
    """Create a SynthesizerEngine instance with mocked dependencies."""
    with (
        patch(
            "agents.synthesizer.synthesizer_engine.GPUManager",
            return_value=mock_gpu_manager,
        ),
        patch("agents.synthesizer.synthesizer_engine.AutoTokenizer"),
        patch("agents.synthesizer.synthesizer_engine.AutoModelForSeq2SeqLM"),
        patch("agents.synthesizer.synthesizer_engine.BERTopic"),
        patch("agents.synthesizer.synthesizer_engine.pipeline"),
        patch("agents.synthesizer.synthesizer_engine.TfidfVectorizer"),
        patch("agents.synthesizer.synthesizer_engine.KMeans"),
    ):
        engine = SynthesizerEngine()
        await engine.initialize()
        yield engine
        await engine.close()


class TestSynthesizerEngineInitialization:
    """Test SynthesizerEngine initialization."""

    @pytest.mark.asyncio
    async def test_initialization_success(self, mock_gpu_manager):
        """Test successful initialization."""
        with (
            patch(
                "agents.synthesizer.synthesizer_engine.GPUManager",
                return_value=mock_gpu_manager,
            ),
            patch(
                "agents.synthesizer.synthesizer_engine.AutoTokenizer",
                return_value=StubTokenizer(),
            ),
            patch(
                "agents.synthesizer.synthesizer_engine.AutoModelForSeq2SeqLM",
                return_value=StubModel(),
            ),
            patch(
                "agents.synthesizer.synthesizer_engine.BERTopic",
                return_value=StubBERTopicModel(),
            ),
            patch("agents.synthesizer.synthesizer_engine.pipeline"),
            patch("agents.synthesizer.synthesizer_engine.TfidfVectorizer"),
            patch("agents.synthesizer.synthesizer_engine.KMeans"),
        ):
            engine = SynthesizerEngine()
            await engine.initialize()

            assert engine.gpu_manager == mock_gpu_manager
            assert engine.is_initialized is True
            assert hasattr(engine, "bart_tokenizer")
            assert hasattr(engine, "bart_model")
            assert hasattr(engine, "bertopic_model")

            await engine.close()

    @pytest.mark.asyncio
    async def test_initialization_gpu_unavailable(self):
        """Test initialization when GPU is unavailable."""
        mock_gpu_manager = StubGPUManager()
        mock_gpu_manager.is_available = False

        with patch(
            "agents.synthesizer.synthesizer_engine.GPUManager",
            return_value=mock_gpu_manager,
        ):
            engine = SynthesizerEngine()

            with pytest.raises(RuntimeError, match="GPU unavailable"):
                await engine.initialize()

            assert engine.is_initialized is False

    @pytest.mark.asyncio
    async def test_initialization_model_loading_failure(self, mock_gpu_manager):
        """Test initialization failure due to model loading issues."""
        with (
            patch(
                "agents.synthesizer.synthesizer_engine.GPUManager",
                return_value=mock_gpu_manager,
            ),
            patch(
                "agents.synthesizer.synthesizer_engine.AutoTokenizer",
                side_effect=Exception("Model load failed"),
            ),
        ):
            engine = SynthesizerEngine()

            with pytest.raises(Exception, match="Model load failed"):
                await engine.initialize()

            assert engine.is_initialized is False


class TestSynthesizerEngineClusterArticles:
    """Test SynthesizerEngine cluster_articles method."""

    @pytest.mark.asyncio
    async def test_cluster_articles_success(self, synthesizer_engine):
        """Test successful article clustering."""
        articles = [
            {"content": "Politics news about elections", "id": 1},
            {"content": "Sports news about football", "id": 2},
            {"content": "Another politics article", "id": 3},
        ]

        # Mock BERTopic behavior
        synthesizer_engine.bertopic_model = StubBERTopicModel()

        result = await synthesizer_engine.cluster_articles(articles)

        assert result["status"] == "success"
        assert "clusters" in result
        assert "topic_info" in result
        assert len(result["clusters"]) == len(articles)

    @pytest.mark.asyncio
    async def test_cluster_articles_empty_input(self, synthesizer_engine):
        """Test clustering with empty article list."""
        result = await synthesizer_engine.cluster_articles([])

        assert result["status"] == "success"
        assert result["clusters"] == []
        assert result["topic_info"] == []

    @pytest.mark.asyncio
    async def test_cluster_articles_fallback_to_kmeans(self, synthesizer_engine):
        """Test clustering fallback to KMeans when BERTopic fails."""
        articles = [{"content": "Test content", "id": 1}]

        # Make BERTopic fail
        synthesizer_engine.bertopic_model.fit_transform = Mock(
            side_effect=Exception("BERTopic failed")
        )

        # Mock KMeans fallback
        mock_kmeans = Mock()
        mock_kmeans.fit_predict.return_value = [0]
        synthesizer_engine.kmeans_model = mock_kmeans

        result = await synthesizer_engine.cluster_articles(articles)

        assert result["status"] == "success"
        assert len(result["clusters"]) == 1

    @pytest.mark.asyncio
    async def test_cluster_articles_clustering_failure(self, synthesizer_engine):
        """Test clustering when all methods fail."""
        articles = [{"content": "Test content", "id": 1}]

        # Make both BERTopic and KMeans fail
        synthesizer_engine.bertopic_model.fit_transform = Mock(
            side_effect=Exception("BERTopic failed")
        )
        synthesizer_engine.kmeans_model = None

        result = await synthesizer_engine.cluster_articles(articles)

        assert result["status"] == "error"
        assert "clustering_failed" in result["error"]


class TestSynthesizerEngineNeutralizeText:
    """Test SynthesizerEngine neutralize_text method."""

    @pytest.mark.asyncio
    async def test_neutralize_text_success(self, synthesizer_engine):
        """Test successful text neutralization."""
        text = "This biased article contains inflammatory content."

        # Mock FLAN-T5 model
        mock_pipeline = Mock()
        mock_pipeline.return_value = [
            {"generated_text": "This neutral article contains factual content."}
        ]
        synthesizer_engine.neutralization_pipeline = mock_pipeline

        result = await synthesizer_engine.neutralize_text(text)

        assert result["status"] == "success"
        assert "neutralized_text" in result
        assert (
            result["neutralized_text"]
            == "This neutral article contains factual content."
        )

    @pytest.mark.asyncio
    async def test_neutralize_text_empty_input(self, synthesizer_engine):
        """Test neutralization with empty text."""
        result = await synthesizer_engine.neutralize_text("")

        assert result["status"] == "success"
        assert result["neutralized_text"] == ""

    @pytest.mark.asyncio
    async def test_neutralize_text_pipeline_failure(self, synthesizer_engine):
        """Test neutralization when pipeline fails."""
        text = "Test text"

        # Make pipeline fail
        synthesizer_engine.neutralization_pipeline = Mock(
            side_effect=Exception("Pipeline failed")
        )

        result = await synthesizer_engine.neutralize_text(text)

        assert result["status"] == "error"
        assert "neutralization_failed" in result["error"]


class TestSynthesizerEngineAggregateCluster:
    """Test SynthesizerEngine aggregate_cluster method."""

    @pytest.mark.asyncio
    async def test_aggregate_cluster_success(self, synthesizer_engine):
        """Test successful cluster aggregation."""
        articles = [
            {"content": "Article one content", "title": "Title 1", "id": 1},
            {"content": "Article two content", "title": "Title 2", "id": 2},
        ]

        # Mock BART model for summarization
        synthesizer_engine.bart_tokenizer = StubTokenizer()
        synthesizer_engine.bart_model = StubModel()

        result = await synthesizer_engine.aggregate_cluster(articles)

        assert result["status"] == "success"
        assert "body" in result
        assert "summary" in result
        assert "key_points" in result
        assert result["article_count"] == len(articles)

    @pytest.mark.asyncio
    async def test_aggregate_cluster_empty_cluster(self, synthesizer_engine):
        """Test aggregation with empty cluster."""
        result = await synthesizer_engine.aggregate_cluster([])

        assert result["status"] == "success"
        assert result["body"] == ""
        assert result["summary"] == ""
        assert result["key_points"] == []
        assert result["article_count"] == 0

    @pytest.mark.asyncio
    async def test_aggregate_cluster_summarization_failure(self, synthesizer_engine):
        """Test aggregation when summarization fails."""
        articles = [{"content": "Test content", "title": "Test", "id": 1}]

        # Make BART model fail
        synthesizer_engine.bart_model.generate = Mock(
            side_effect=Exception("Summarization failed")
        )

        result = await synthesizer_engine.aggregate_cluster(articles)

        assert result["status"] == "error"
        assert "aggregation_failed" in result["error"]


class TestSynthesizerEngineSynthesizeGPU:
    """Test SynthesizerEngine synthesize_gpu method."""

    @pytest.mark.asyncio
    async def test_synthesize_gpu_success(self, synthesizer_engine):
        """Test successful GPU synthesis."""
        articles = [
            {"content": "GPU accelerated content synthesis test", "id": 1},
            {"content": "Another article for synthesis", "id": 2},
        ]

        # Mock all required components
        synthesizer_engine.bertopic_model = StubBERTopicModel()
        synthesizer_engine.neutralization_pipeline = Mock(
            return_value=[{"generated_text": "Neutral text"}]
        )
        synthesizer_engine.bart_tokenizer = StubTokenizer()
        synthesizer_engine.bart_model = StubModel()

        result = await synthesizer_engine.synthesize_gpu(articles)

        assert result["status"] == "success"
        assert "clusters" in result
        assert "synthesized_content" in result
        assert "processing_stats" in result

    @pytest.mark.asyncio
    async def test_synthesize_gpu_with_options(self, synthesizer_engine):
        """Test GPU synthesis with processing options."""
        articles = [{"content": "Test content", "id": 1}]

        # Mock components
        synthesizer_engine.bertopic_model = StubBERTopicModel()
        synthesizer_engine.neutralization_pipeline = Mock(
            return_value=[{"generated_text": "Neutral"}]
        )
        synthesizer_engine.bart_tokenizer = StubTokenizer()
        synthesizer_engine.bart_model = StubModel()

        options = {
            "neutralize_bias": True,
            "max_clusters": 5,
            "summarize_clusters": True,
        }

        result = await synthesizer_engine.synthesize_gpu(articles, options=options)

        assert result["status"] == "success"
        # Verify options were applied (implementation dependent)

    @pytest.mark.asyncio
    async def test_synthesize_gpu_clustering_failure(self, synthesizer_engine):
        """Test GPU synthesis when clustering fails."""
        articles = [{"content": "Test content", "id": 1}]

        # Make clustering fail
        synthesizer_engine.bertopic_model.fit_transform = Mock(
            side_effect=Exception("Clustering failed")
        )

        result = await synthesizer_engine.synthesize_gpu(articles)

        assert result["status"] == "error"
        assert "synthesis_failed" in result["error"]

    @pytest.mark.asyncio
    async def test_synthesize_gpu_memory_pressure(
        self, synthesizer_engine, mock_gpu_manager
    ):
        """Test GPU synthesis under memory pressure."""
        articles = [{"content": "Test", "id": 1}]

        # Simulate low GPU memory (make method a Mock so tests can adjust return)
        from unittest.mock import Mock as _Mock

        mock_gpu_manager.get_available_memory = _Mock(
            return_value=1 * 1024 * 1024 * 1024
        )  # 1GB

        # Mock components
        synthesizer_engine.bertopic_model = StubBERTopicModel()
        synthesizer_engine.neutralization_pipeline = Mock(
            return_value=[{"generated_text": "Neutral"}]
        )
        synthesizer_engine.bart_tokenizer = StubTokenizer()
        synthesizer_engine.bart_model = StubModel()

        result = await synthesizer_engine.synthesize_gpu(articles)

        # Should still succeed but may use CPU fallback
        assert result["status"] in ["success", "partial_success"]


class TestSynthesizerEngineClose:
    """Test SynthesizerEngine close method."""

    @pytest.mark.asyncio
    async def test_close_success(self, synthesizer_engine):
        """Test successful engine closure."""
        await synthesizer_engine.close()

        assert synthesizer_engine.is_initialized is False

    @pytest.mark.asyncio
    async def test_close_idempotent(self, synthesizer_engine):
        """Test that close can be called multiple times safely."""
        await synthesizer_engine.close()
        await synthesizer_engine.close()  # Should not raise

        assert synthesizer_engine.is_initialized is False


class TestSynthesizerEngineErrorHandling:
    """Test SynthesizerEngine error handling across methods."""

    @pytest.mark.asyncio
    async def test_uninitialized_engine_operations(self):
        """Test operations on uninitialized engine."""
        engine = SynthesizerEngine()  # Not initialized

        with pytest.raises(RuntimeError, match="not initialized"):
            await engine.cluster_articles([])

        with pytest.raises(RuntimeError, match="not initialized"):
            await engine.neutralize_text("text")

        with pytest.raises(RuntimeError, match="not initialized"):
            await engine.synthesize_gpu([])

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, synthesizer_engine):
        """Test concurrent operations on the engine."""
        # Mock components for concurrent calls
        synthesizer_engine.bertopic_model = StubBERTopicModel()
        synthesizer_engine.neutralization_pipeline = Mock(
            return_value=[{"generated_text": "Neutral"}]
        )
        synthesizer_engine.bart_tokenizer = StubTokenizer()
        synthesizer_engine.bart_model = StubModel()

        # Run multiple operations concurrently
        tasks = []
        for i in range(3):
            articles = [{"content": f"Content {i}", "id": i}]
            task = synthesizer_engine.synthesize_gpu(articles)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All should succeed
        for result in results:
            assert not isinstance(result, Exception)
            assert result["status"] == "success"


class TestSynthesizerEngineResourceManagement:
    """Test SynthesizerEngine resource management."""

    @pytest.mark.asyncio
    async def test_memory_cleanup_on_failure(self, synthesizer_engine):
        """Test that resources are cleaned up on operation failure."""
        articles = [{"content": "Test", "id": 1}]

        # Make operation fail midway
        synthesizer_engine.bertopic_model.fit_transform = Mock(
            side_effect=Exception("Mid-operation failure")
        )

        result = await synthesizer_engine.synthesize_gpu(articles)

        assert result["status"] == "error"
        # Engine should still be in valid state for subsequent operations
        assert synthesizer_engine.is_initialized is True

    @pytest.mark.asyncio
    async def test_gpu_device_assignment(self, synthesizer_engine, mock_gpu_manager):
        """Test proper GPU device assignment to models."""
        # Verify models are moved to GPU device during initialization
        assert synthesizer_engine.bart_model.device == mock_gpu_manager.get_device()

    @pytest.mark.asyncio
    async def test_batch_processing_limits(self, synthesizer_engine):
        """Test batch processing with size limits."""
        # Create many articles to test batching
        articles = [{"content": f"Article content {i}", "id": i} for i in range(100)]

        # Mock components
        synthesizer_engine.bertopic_model = StubBERTopicModel()
        synthesizer_engine.neutralization_pipeline = Mock(
            return_value=[{"generated_text": "Neutral"}] * 100
        )
        synthesizer_engine.bart_tokenizer = StubTokenizer()
        synthesizer_engine.bart_model = StubModel()

        result = await synthesizer_engine.synthesize_gpu(articles)

        assert result["status"] == "success"
        # Should handle large batches without memory issues
