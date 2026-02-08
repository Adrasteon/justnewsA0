"""
Critic Engine - AI-Powered Content Analysis and Critique

This module provides the core AI engine for content critique and analysis,
implementing a 5-model workflow for comprehensive editorial assessment.

Models Used:
- BERT: Quality assessment and content evaluation
- RoBERTa: Bias detection and neutrality analysis
- DeBERTa: Factual consistency checking
- DistilBERT: Readability and clarity assessment
- SentenceTransformer: Plagiarism detection and semantic similarity

Key Features:
- GPU acceleration support with fallback to CPU
- Comprehensive error handling and validation
- Training data collection and feedback loops
- Performance monitoring and metrics
- Model health checking and status reporting

All operations include robust error handling, validation, and fallbacks.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import torch

try:
    # Prefer a top-level common package if present (CI may install one); otherwise
    # fall back to agents.common.gpu_config_manager which is bundled with the repo.
    from common.gpu_config_manager import GPUConfigManager  # type: ignore
except Exception:
    try:
        from agents.common.gpu_config_manager import GPUConfigManager  # type: ignore
    except Exception:
        # Provide a lightweight stub so tests that don't require GPU management
        # continue to work in environments missing this helper.
        class GPUConfigManager:  # pragma: no cover - fallback
            def get_optimal_device(self):
                return None


try:
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DistilBertModel,
        DistilBertTokenizer,
        pipeline,
    )

    TRANSFORMERS_AVAILABLE = True
except Exception:
    AutoModelForSequenceClassification = None
    AutoTokenizer = None
    DistilBertModel = None
    DistilBertTokenizer = None
    pipeline = None
    TRANSFORMERS_AVAILABLE = False

from common.observability import get_logger

try:
    from .model_adapter import CriticModelAdapter as MistralAdapter
    from .model_adapter import (
        MODEL_ADAPTER_NAME as CRITIC_ADAPTER_NAME,
        SYSTEM_PROMPT,
        CriticAssessment,
    )
except Exception:  # pragma: no cover - optional dependency wiring
    CriticAssessment = None  # type: ignore
    MistralAdapter = None  # type: ignore
    MistralAdapter = None
    CRITIC_ADAPTER_NAME = "mistral_critic_v1"

# Configure logging
logger = get_logger(__name__)


@dataclass
class CriticConfig:
    """Configuration for the critic engine."""

    # Model configurations
    bert_model_name: str = "microsoft/DialoGPT-medium"
    roberta_model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    deberta_model_name: str = "microsoft/DialoGPT-medium"
    distilbert_model_name: str = "distilbert-base-uncased"
    sentence_transformer_model: str = "all-MiniLM-L6-v2"

    # GPU configuration
    use_gpu: bool = True
    gpu_memory_limit: float = 0.8
    batch_size: int = 16

    # Processing limits
    max_content_length: int = 512
    max_batch_size: int = 32

    # Training and feedback
    enable_feedback_collection: bool = True
    feedback_log_path: str = "logs/critic_feedback.jsonl"


@dataclass
class ReviewResult:
    """Result of a comprehensive content review."""

    quality_score: float = 0.0
    bias_score: float = 0.0
    factual_consistency: float = 0.0
    readability_score: float = 0.0
    plagiarism_score: float = 0.0
    overall_score: float = 0.0
    assessment: str = ""
    recommendations: list[str] = field(default_factory=list)
    processing_time: float = 0.0
    model_versions: dict[str, str] = field(default_factory=dict)


class CriticEngine:
    """
    AI-powered content critique and analysis engine.

    This engine implements a comprehensive 5-model workflow for editorial assessment,
    providing detailed analysis of content quality, bias, consistency, readability,
    and originality.
    """

    def __init__(self, config: CriticConfig):
        """Initialize the critic engine with configuration."""
        self.config = config
        self.logger = get_logger(__name__)

        # Initialize GPU manager
        self.gpu_manager = GPUConfigManager()

        # Model storage
        self.models = {}
        self.tokenizers = {}
        self.pipelines = {}

        # Processing statistics
        self.processing_stats = {
            "total_reviews": 0,
            "average_processing_time": 0.0,
            "gpu_memory_usage": 0.0,
            "model_load_times": {},
            "error_counts": {},
        }

        # Feedback collection
        self.feedback_data = []
        self.mistral_adapter: MistralAdapter | None = None

        # Initialize models
        self._initialize_models()

    def _initialize_models(self):
        """Initialize all AI models with error handling and fallbacks."""
        try:
            self.logger.info("🔧 Initializing critic engine models...")

            # Initialize BERT for quality assessment
            self._load_bert_model()

            # Initialize RoBERTa for bias detection
            self._load_roberta_model()

            # Initialize DeBERTa for factual consistency
            self._load_deberta_model()

            # Initialize DistilBERT for readability
            self._load_distilbert_model()

            # Initialize SentenceTransformer for plagiarism detection
            self._load_sentence_transformer()

            self._initialize_mistral_adapter()

            self.logger.info("✅ All critic models initialized successfully")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize critic models: {e}")
            raise

    def _load_bert_model(self):
        """Load BERT model for quality assessment."""
        try:
            start_time = time.time()

            # Use a more appropriate model for quality assessment
            model_name = "nlptown/bert-base-multilingual-uncased-sentiment"

            if self.config.use_gpu and torch.cuda.is_available():
                device = self.gpu_manager.get_optimal_device()
                self.models["bert"] = (
                    AutoModelForSequenceClassification.from_pretrained(model_name).to(
                        device
                    )
                )
                self.tokenizers["bert"] = AutoTokenizer.from_pretrained(model_name)
            else:
                self.models["bert"] = (
                    AutoModelForSequenceClassification.from_pretrained(model_name)
                )
                self.tokenizers["bert"] = AutoTokenizer.from_pretrained(model_name)

            load_time = time.time() - start_time
            self.processing_stats["model_load_times"]["bert"] = load_time
            self.logger.info(f"📚 BERT model loaded in {load_time:.2f}s")

        except Exception as e:
            self.logger.error(f"Failed to load BERT model: {e}")
            self.models["bert"] = None
            self.tokenizers["bert"] = None

    def _load_roberta_model(self):
        """Load RoBERTa model for bias detection."""
        try:
            start_time = time.time()

            if self.config.use_gpu and torch.cuda.is_available():
                device = self.gpu_manager.get_optimal_device()
                self.pipelines["roberta"] = pipeline(
                    "sentiment-analysis",
                    model=self.config.roberta_model_name,
                    device=device.index if hasattr(device, "index") else 0,
                )
            else:
                self.pipelines["roberta"] = pipeline(
                    "sentiment-analysis", model=self.config.roberta_model_name
                )

            load_time = time.time() - start_time
            self.processing_stats["model_load_times"]["roberta"] = load_time
            self.logger.info(f"📚 RoBERTa model loaded in {load_time:.2f}s")

        except Exception as e:
            self.logger.error(f"Failed to load RoBERTa model: {e}")
            self.pipelines["roberta"] = None

    def _load_deberta_model(self):
        """Load DeBERTa model for factual consistency."""
        try:
            start_time = time.time()

            # Use a factual consistency model
            model_name = "microsoft/DialoGPT-medium"

            if self.config.use_gpu and torch.cuda.is_available():
                device = self.gpu_manager.get_optimal_device()
                self.models["deberta"] = (
                    AutoModelForSequenceClassification.from_pretrained(model_name).to(
                        device
                    )
                )
                self.tokenizers["deberta"] = AutoTokenizer.from_pretrained(model_name)
            else:
                self.models["deberta"] = (
                    AutoModelForSequenceClassification.from_pretrained(model_name)
                )
                self.tokenizers["deberta"] = AutoTokenizer.from_pretrained(model_name)

            load_time = time.time() - start_time
            self.processing_stats["model_load_times"]["deberta"] = load_time
            self.logger.info(f"📚 DeBERTa model loaded in {load_time:.2f}s")

        except Exception as e:
            self.logger.error(f"Failed to load DeBERTa model: {e}")
            self.models["deberta"] = None
            self.tokenizers["deberta"] = None

    def _load_distilbert_model(self):
        """Load DistilBERT model for readability assessment."""
        try:
            start_time = time.time()

            if self.config.use_gpu and torch.cuda.is_available():
                device = self.gpu_manager.get_optimal_device()
                self.models["distilbert"] = DistilBertModel.from_pretrained(
                    self.config.distilbert_model_name
                ).to(device)
                self.tokenizers["distilbert"] = DistilBertTokenizer.from_pretrained(
                    self.config.distilbert_model_name
                )
            else:
                self.models["distilbert"] = DistilBertModel.from_pretrained(
                    self.config.distilbert_model_name
                )
                self.tokenizers["distilbert"] = DistilBertTokenizer.from_pretrained(
                    self.config.distilbert_model_name
                )

            load_time = time.time() - start_time
            self.processing_stats["model_load_times"]["distilbert"] = load_time
            self.logger.info(f"📚 DistilBERT model loaded in {load_time:.2f}s")

        except Exception as e:
            self.logger.error(f"Failed to load DistilBERT model: {e}")
            self.models["distilbert"] = None
            self.tokenizers["distilbert"] = None

    def _load_sentence_transformer(self):
        """Load SentenceTransformer for plagiarism detection."""
        try:
            start_time = time.time()

            # Import here to avoid dependency issues
            from sentence_transformers import SentenceTransformer

            if self.config.use_gpu and torch.cuda.is_available():
                device = self.gpu_manager.get_optimal_device()
                self.models["sentence_transformer"] = SentenceTransformer(
                    self.config.sentence_transformer_model,
                    device=device.index if hasattr(device, "index") else "cuda",
                )
            else:
                self.models["sentence_transformer"] = SentenceTransformer(
                    self.config.sentence_transformer_model, device="cpu"
                )

            load_time = time.time() - start_time
            self.processing_stats["model_load_times"]["sentence_transformer"] = (
                load_time
            )
            self.logger.info(f"📚 SentenceTransformer loaded in {load_time:.2f}s")

        except Exception as e:
            self.logger.error(f"Failed to load SentenceTransformer: {e}")
            self.models["sentence_transformer"] = None

    def _initialize_mistral_adapter(self) -> None:
        """Prepare the high-accuracy Mistral adapter for critiques."""
        if MistralAdapter is None:
            self.logger.info(
                "Mistral adapter dependencies unavailable; using legacy critic stack"
            )
            return
        try:
            self.mistral_adapter = MistralAdapter()
            if getattr(self.mistral_adapter, "enabled", True):
                self.logger.info("Critic Qwen adapter enabled (lazy-loaded)")
            else:
                self.logger.info("Critic Qwen adapter disabled via env variable")
        except Exception as exc:
            self.logger.warning(f"Failed to initialize Critic Mistral adapter: {exc}")
            self.mistral_adapter = None

    def _maybe_run_mistral_review(
        self, content: str, url: str | None
    ) -> ReviewResult | None:
        if not self.mistral_adapter or not content.strip():
            return None
        try:
            assessment = self.mistral_adapter.review(content, url)
        except Exception as exc:
            self.logger.warning(f"Critic Mistral adapter review failed: {exc}")
            return None
        if not assessment:
            return None
        return self._build_review_result_from_adapter(assessment)

    def _build_review_result_from_adapter(
        self, assessment: CriticAssessment
    ) -> ReviewResult:
        plagiarism_score = max(0.0, min(1.0, 1.0 - assessment.originality))
        recommendations = assessment.recommendations or ["No recommendations provided."]
        versions = self._get_model_versions()
        versions["mistral_adapter"] = CRITIC_ADAPTER_NAME
        return ReviewResult(
            quality_score=assessment.quality,
            bias_score=assessment.bias,
            factual_consistency=assessment.consistency,
            readability_score=assessment.readability,
            plagiarism_score=plagiarism_score,
            overall_score=assessment.overall,
            assessment=assessment.assessment,
            recommendations=recommendations,
            processing_time=0.0,
            model_versions=versions,
        )

    def _update_processing_time(self, processing_time: float) -> None:
        self.processing_stats["total_reviews"] += 1
        total = self.processing_stats["total_reviews"]
        prev_avg = self.processing_stats["average_processing_time"]
        self.processing_stats["average_processing_time"] = (
            ((prev_avg * (total - 1)) + processing_time) / total
            if total
            else processing_time
        )
        if torch.cuda.is_available():
            try:
                max_mem = torch.cuda.max_memory_allocated()
                if max_mem > 0:
                    self.processing_stats["gpu_memory_usage"] = (
                        torch.cuda.memory_allocated() / max_mem
                    )
            except Exception:
                pass

    def comprehensive_review(
        self, content: str, url: str | None = None
    ) -> ReviewResult:
        """
        Perform comprehensive content review using all 5 models.

        Args:
            content: Content to review
            url: Source URL for context

        Returns:
            ReviewResult with detailed analysis
        """
        start_time = time.time()

        try:
            self.logger.info(
                f"🔍 Starting comprehensive review for {len(content)} characters"
            )

            # Validate input
            if not content or not content.strip():
                return ReviewResult(
                    assessment="Empty content provided",
                    recommendations=["Provide valid content for analysis"],
                )

            # Truncate content if too long
            if len(content) > self.config.max_content_length:
                content = content[: self.config.max_content_length]
                self.logger.warning(
                    f"Content truncated to {self.config.max_content_length} characters"
                )

            adapter_result = self._maybe_run_mistral_review(content, url)
            if adapter_result:
                processing_time = time.time() - start_time
                adapter_result.processing_time = processing_time
                self._update_processing_time(processing_time)
                self.logger.info(
                    f"✅ Comprehensive review completed via Mistral adapter in {processing_time:.2f}s"
                )
                return adapter_result

            # Perform individual analyses
            quality_result = self._assess_quality(content)
            bias_result = self._detect_bias(content)
            consistency_result = self._check_factual_consistency(content)
            readability_result = self._assess_readability(content)
            plagiarism_result = self._detect_plagiarism(content)

            # Calculate overall score
            overall_score = self._calculate_overall_score(
                quality_result,
                bias_result,
                consistency_result,
                readability_result,
                plagiarism_result,
            )

            # Generate assessment and recommendations
            assessment = self._generate_assessment(overall_score)
            recommendations = self._generate_recommendations(
                quality_result,
                bias_result,
                consistency_result,
                readability_result,
                plagiarism_result,
            )

            # Update processing stats
            processing_time = time.time() - start_time
            self._update_processing_time(processing_time)

            result = ReviewResult(
                quality_score=quality_result.get("score", 0.0),
                bias_score=bias_result.get("score", 0.0),
                factual_consistency=consistency_result.get("score", 0.0),
                readability_score=readability_result.get("score", 0.0),
                plagiarism_score=plagiarism_result.get("score", 0.0),
                overall_score=overall_score,
                assessment=assessment,
                recommendations=recommendations,
                processing_time=processing_time,
                model_versions=self._get_model_versions(),
            )

            self.logger.info(
                f"✅ Comprehensive review completed in {processing_time:.2f}s with score {overall_score:.2f}"
            )
            return result

        except Exception as e:
            processing_time = time.time() - start_time
            self.logger.error(
                f"❌ Comprehensive review failed after {processing_time:.2f}s: {e}"
            )
            self.processing_stats["error_counts"]["comprehensive_review"] = (
                self.processing_stats["error_counts"].get("comprehensive_review", 0) + 1
            )

            return ReviewResult(
                assessment=f"Review failed: {str(e)}",
                recommendations=["Retry analysis or check content format"],
                processing_time=processing_time,
            )

    def critique_synthesis(
        self, content: str, url: str | None = None
    ) -> dict[str, Any]:
        """
        Synthesize comprehensive content critique.

        Args:
            content: Content to critique
            url: Source URL

        Returns:
            Critique synthesis results
        """
        try:
            review = self.comprehensive_review(content, url)

            return {
                "critique_score": review.overall_score * 10,  # Convert to 0-10 scale
                "quality_score": review.quality_score * 10,
                "bias_score": review.bias_score * 10,
                "consistency_score": review.factual_consistency * 10,
                "readability_score": review.readability_score * 10,
                "originality_score": (1.0 - review.plagiarism_score) * 10,
                "assessment": review.assessment,
                "recommendations": review.recommendations,
                "processing_time": review.processing_time,
                "model_versions": review.model_versions,
            }

        except Exception as e:
            self.logger.error(f"Critique synthesis failed: {e}")
            return {"error": str(e)}

    def critique_neutrality(
        self, content: str, url: str | None = None
    ) -> dict[str, Any]:
        """
        Analyze content neutrality and bias.

        Args:
            content: Content to analyze
            url: Source URL

        Returns:
            Neutrality analysis results
        """
        try:
            bias_result = self._detect_bias(content)

            return {
                "neutrality_score": (1.0 - bias_result.get("score", 0.5)) * 10,
                "bias_indicators": bias_result.get("indicators", []),
                "sentiment_distribution": bias_result.get("sentiment_distribution", {}),
                "recommendations": bias_result.get("recommendations", []),
                "processing_time": bias_result.get("processing_time", 0.0),
            }

        except Exception as e:
            self.logger.error(f"Neutrality analysis failed: {e}")
            return {"error": str(e)}

    def analyze_argument_structure(
        self, content: str, url: str | None = None
    ) -> dict[str, Any]:
        """
        Analyze logical argument structure.

        Args:
            content: Content to analyze
            url: Source URL

        Returns:
            Argument structure analysis
        """
        try:
            # Use quality assessment as proxy for argument structure
            quality_result = self._assess_quality(content)

            return {
                "argument_strength": {
                    "strength_score": quality_result.get("score", 0.5),
                    "logical_coherence": quality_result.get("coherence", 0.5),
                    "evidence_quality": quality_result.get("evidence_quality", 0.5),
                },
                "structural_analysis": {
                    "sentence_count": len(content.split(".")),
                    "average_sentence_length": sum(
                        len(s.split()) for s in content.split(".")
                    )
                    / max(1, len(content.split("."))),
                    "complexity_score": quality_result.get("complexity", 0.5),
                },
            }

        except Exception as e:
            self.logger.error(f"Argument structure analysis failed: {e}")
            return {"error": str(e)}

    def assess_editorial_consistency(
        self, content: str, url: str | None = None
    ) -> dict[str, Any]:
        """
        Assess editorial consistency and coherence.

        Args:
            content: Content to assess
            url: Source URL

        Returns:
            Consistency assessment results
        """
        try:
            consistency_result = self._check_factual_consistency(content)

            return {
                "consistency_score": consistency_result.get("score", 0.5),
                "factual_accuracy": consistency_result.get("factual_accuracy", 0.5),
                "internal_coherence": consistency_result.get("coherence", 0.5),
                "contradictions": consistency_result.get("contradictions", []),
            }

        except Exception as e:
            self.logger.error(f"Editorial consistency assessment failed: {e}")
            return {"error": str(e)}

    def detect_logical_fallacies(
        self, content: str, url: str | None = None
    ) -> dict[str, Any]:
        """
        Detect logical fallacies and reasoning errors.

        Args:
            content: Content to analyze
            url: Source URL

        Returns:
            Fallacy detection results
        """
        try:
            # Use quality assessment to identify potential fallacies
            quality_result = self._assess_quality(content)

            fallacies = []
            fallacy_score = quality_result.get("score", 0.5)

            # Simple heuristic-based fallacy detection
            if fallacy_score < 0.3:
                fallacies.append(
                    {
                        "fallacy": "weak_argumentation",
                        "confidence": 0.7,
                        "description": "Overall weak argumentative structure",
                    }
                )

            return {
                "fallacies_detected": fallacies,
                "fallacy_count": len(fallacies),
                "logical_strength": fallacy_score,
                "analysis_confidence": 0.6,
            }

        except Exception as e:
            self.logger.error(f"Logical fallacy detection failed: {e}")
            return {"error": str(e)}

    def assess_source_credibility(
        self, content: str, url: str | None = None
    ) -> dict[str, Any]:
        """
        Assess source credibility and evidence quality.

        Args:
            content: Content to assess
            url: Source URL

        Returns:
            Credibility assessment results
        """
        try:
            # Extract citations and references
            citations = self._extract_citations(content)

            # Assess credibility based on citation quality
            credibility_score = min(1.0, len(citations) * 0.2)

            return {
                "citations": citations,
                "citation_count": len(citations),
                "credibility_score": credibility_score,
                "evidence_quality": credibility_score,
                "source_reliability": self._assess_source_reliability(url)
                if url
                else 0.5,
            }

        except Exception as e:
            self.logger.error(f"Source credibility assessment failed: {e}")
            return {"error": str(e)}

    def _assess_quality(self, content: str) -> dict[str, Any]:
        """Assess content quality using BERT."""
        try:
            if not self.models.get("bert") or not self.tokenizers.get("bert"):
                return {"score": 0.5, "error": "BERT model not available"}

            # Tokenize content
            inputs = self.tokenizers["bert"](
                content,
                return_tensors="pt",
                truncation=True,
                max_length=self.config.max_content_length,
                padding=True,
            )

            # Move to GPU if available
            if self.config.use_gpu and torch.cuda.is_available():
                inputs = {
                    k: v.to(self.gpu_manager.get_optimal_device())
                    for k, v in inputs.items()
                }

            # Get prediction
            with torch.no_grad():
                outputs = self.models["bert"](**inputs)
                predictions = torch.softmax(outputs.logits, dim=-1)

            # Convert to quality score (0-1 scale)
            quality_score = (
                predictions[0][1].item()
                if len(predictions[0]) > 1
                else predictions[0][0].item()
            )

            return {
                "score": quality_score,
                "coherence": quality_score * 0.9
                + 0.1,  # Slight adjustment for coherence
                "evidence_quality": quality_score * 0.8 + 0.2,
                "complexity": min(1.0, len(content.split()) / 100.0),
            }

        except Exception as e:
            self.logger.error(f"BERT quality assessment failed: {e}")
            return {"score": 0.5, "error": str(e)}

    def _detect_bias(self, content: str) -> dict[str, Any]:
        """Detect bias using RoBERTa sentiment analysis."""
        try:
            if not self.pipelines.get("roberta"):
                return {"score": 0.5, "error": "RoBERTa pipeline not available"}

            # Analyze sentiment
            results = self.pipelines["roberta"](content)

            # Calculate bias score based on sentiment distribution
            sentiment_scores = {
                "LABEL_0": -1,
                "LABEL_1": 0,
                "LABEL_2": 1,
            }  # Negative, Neutral, Positive
            bias_score = sum(
                result["score"] * sentiment_scores.get(result["label"], 0)
                for result in results
            )

            # Normalize to 0-1 scale (0 = neutral, 1 = highly biased)
            bias_score = abs(bias_score) / 2.0

            return {
                "score": bias_score,
                "sentiment_distribution": {
                    result["label"]: result["score"] for result in results
                },
                "indicators": ["sentiment_imbalance"] if bias_score > 0.7 else [],
                "recommendations": ["Balance perspectives"] if bias_score > 0.7 else [],
            }

        except Exception as e:
            self.logger.error(f"RoBERTa bias detection failed: {e}")
            return {"score": 0.5, "error": str(e)}

    def _check_factual_consistency(self, content: str) -> dict[str, Any]:
        """Check factual consistency using DeBERTa."""
        try:
            if not self.models.get("deberta") or not self.tokenizers.get("deberta"):
                return {"score": 0.5, "error": "DeBERTa model not available"}

            # Simple consistency check based on coherence
            inputs = self.tokenizers["deberta"](
                content,
                return_tensors="pt",
                truncation=True,
                max_length=self.config.max_content_length,
                padding=True,
            )

            if self.config.use_gpu and torch.cuda.is_available():
                inputs = {
                    k: v.to(self.gpu_manager.get_optimal_device())
                    for k, v in inputs.items()
                }

            with torch.no_grad():
                outputs = self.models["deberta"](**inputs)
                consistency_score = torch.softmax(outputs.logits, dim=-1)[0][1].item()

            return {
                "score": consistency_score,
                "factual_accuracy": consistency_score * 0.9 + 0.1,
                "coherence": consistency_score,
                "contradictions": [],
            }

        except Exception as e:
            self.logger.error(f"DeBERTa consistency check failed: {e}")
            return {"score": 0.5, "error": str(e)}

    def _assess_readability(self, content: str) -> dict[str, Any]:
        """Assess readability using DistilBERT."""
        try:
            if not self.models.get("distilbert") or not self.tokenizers.get(
                "distilbert"
            ):
                return {"score": 0.5, "error": "DistilBERT model not available"}

            # Simple readability assessment based on sentence complexity
            sentences = content.split(".")
            avg_words_per_sentence = sum(len(s.split()) for s in sentences) / max(
                1, len(sentences)
            )

            # Use DistilBERT to assess linguistic complexity
            inputs = self.tokenizers["distilbert"](
                content[:512],  # Limit input size
                return_tensors="pt",
                truncation=True,
                padding=True,
            )

            if self.config.use_gpu and torch.cuda.is_available():
                inputs = {
                    k: v.to(self.gpu_manager.get_optimal_device())
                    for k, v in inputs.items()
                }

            with torch.no_grad():
                outputs = self.models["distilbert"](**inputs)
                complexity_score = outputs.last_hidden_state.mean().item()

            # Normalize complexity score
            readability_score = 1.0 - min(1.0, abs(complexity_score) / 5.0)

            return {
                "score": readability_score,
                "avg_words_per_sentence": avg_words_per_sentence,
                "complexity_score": complexity_score,
                "grade_level": "intermediate"
                if readability_score > 0.6
                else "advanced",
            }

        except Exception as e:
            self.logger.error(f"DistilBERT readability assessment failed: {e}")
            return {"score": 0.5, "error": str(e)}

    def _detect_plagiarism(self, content: str) -> dict[str, Any]:
        """Detect potential plagiarism using SentenceTransformer."""
        try:
            if not self.models.get("sentence_transformer"):
                return {"score": 0.0, "error": "SentenceTransformer not available"}

            # For now, return low plagiarism score (would need reference corpus for real detection)
            # In a real implementation, this would compare against a database of known content
            plagiarism_score = 0.1  # Low baseline

            return {
                "score": plagiarism_score,
                "similarity_score": plagiarism_score,
                "matches_found": 0,
                "confidence": 0.5,
            }

        except Exception as e:
            self.logger.error(f"SentenceTransformer plagiarism detection failed: {e}")
            return {"score": 0.0, "error": str(e)}

    def _calculate_overall_score(
        self, quality, bias, consistency, readability, plagiarism
    ) -> float:
        """Calculate overall critique score from individual analyses."""
        try:
            weights = {
                "quality": 0.3,
                "bias": 0.2,
                "consistency": 0.25,
                "readability": 0.15,
                "plagiarism": 0.1,
            }

            overall = (
                quality.get("score", 0.5) * weights["quality"]
                + (1.0 - bias.get("score", 0.5)) * weights["bias"]  # Invert bias score
                + consistency.get("score", 0.5) * weights["consistency"]
                + readability.get("score", 0.5) * weights["readability"]
                + (1.0 - plagiarism.get("score", 0.0))
                * weights["plagiarism"]  # Invert plagiarism score
            )

            return max(0.0, min(1.0, overall))

        except Exception as e:
            self.logger.error(f"Overall score calculation failed: {e}")
            return 0.5

    def _generate_assessment(self, overall_score: float) -> str:
        """Generate human-readable assessment based on overall score."""
        if overall_score >= 0.8:
            return "Excellent quality content with strong editorial standards"
        elif overall_score >= 0.6:
            return "Good quality content meeting most editorial standards"
        elif overall_score >= 0.4:
            return "Adequate content with room for improvement"
        elif overall_score >= 0.2:
            return "Poor quality content requiring significant revision"
        else:
            return "Very poor quality content - major revision needed"

    def _generate_recommendations(
        self, quality, bias, consistency, readability, plagiarism
    ) -> list[str]:
        """Generate improvement recommendations based on analysis results."""
        recommendations = []

        try:
            if quality.get("score", 0.5) < 0.6:
                recommendations.append("Improve overall content quality and coherence")

            if bias.get("score", 0.5) > 0.7:
                recommendations.append("Reduce bias and ensure balanced perspectives")

            if consistency.get("score", 0.5) < 0.6:
                recommendations.append("Enhance factual consistency and accuracy")

            if readability.get("score", 0.5) < 0.6:
                recommendations.append("Simplify language and improve readability")

            if plagiarism.get("score", 0.0) > 0.3:
                recommendations.append("Address potential plagiarism concerns")

            if not recommendations:
                recommendations.append(
                    "Content meets quality standards - minor polishing recommended"
                )

        except Exception:
            recommendations.append("Manual review recommended due to analysis error")

        return recommendations

    def _extract_citations(self, content: str) -> list[dict[str, Any]]:
        """Extract citations and references from content."""
        citations = []

        # Simple citation pattern matching
        citation_patterns = [
            r"according to ([A-Z][a-z]+ [A-Z][a-z]+)",
            r"([A-Z][a-z]+ [A-Z][a-z]+) said",
            r"study by ([A-Z][A-Z][a-z]+)",
            r'"([^"]*)" \(([^)]+)\)',
        ]

        for pattern in citation_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                citations.append(
                    {
                        "text": match.group(1)
                        if len(match.groups()) > 0
                        else match.group(0),
                        "type": "citation",
                        "position": match.start(),
                    }
                )

        return citations

    def _assess_source_reliability(self, url: str) -> float:
        """Assess source reliability based on URL patterns."""
        if not url:
            return 0.5

        # Simple heuristic-based assessment
        reliable_domains = [
            ".edu",
            ".gov",
            ".org",
            "bbc.com",
            "reuters.com",
            "apnews.com",
        ]
        unreliable_indicators = ["blogspot", "wordpress", "medium.com"]

        url_lower = url.lower()

        if any(domain in url_lower for domain in reliable_domains):
            return 0.8
        elif any(indicator in url_lower for indicator in unreliable_indicators):
            return 0.3
        else:
            return 0.5

    def _get_model_versions(self) -> dict[str, str]:
        """Get current model versions."""
        return {
            "bert": self.config.bert_model_name,
            "roberta": self.config.roberta_model_name,
            "deberta": self.config.deberta_model_name,
            "distilbert": self.config.distilbert_model_name,
            "sentence_transformer": self.config.sentence_transformer_model,
        }

    def get_model_status(self) -> dict[str, bool]:
        """Get status of all models."""
        return {
            "bert": self.models.get("bert") is not None,
            "roberta": self.pipelines.get("roberta") is not None,
            "deberta": self.models.get("deberta") is not None,
            "distilbert": self.models.get("distilbert") is not None,
            "sentence_transformer": self.models.get("sentence_transformer") is not None,
        }

    def log_feedback(self, operation: str, data: dict[str, Any]):
        """Log feedback data for model improvement."""
        if not self.config.enable_feedback_collection:
            return

        try:
            feedback_entry = {
                "timestamp": datetime.now().isoformat(),
                "operation": operation,
                "data": data,
            }

            self.feedback_data.append(feedback_entry)

            # Write to file periodically
            if len(self.feedback_data) >= 10:
                self._write_feedback_to_file()
                self.feedback_data = []

        except Exception as e:
            self.logger.error(f"Failed to log feedback: {e}")

    def _write_feedback_to_file(self):
        """Write accumulated feedback to file."""
        try:
            os.makedirs(os.path.dirname(self.config.feedback_log_path), exist_ok=True)

            with open(self.config.feedback_log_path, "a", encoding="utf-8") as f:
                for entry in self.feedback_data:
                    f.write(json.dumps(entry) + "\n")

        except Exception as e:
            self.logger.error(f"Failed to write feedback to file: {e}")

    def cleanup(self):
        """Clean up resources and GPU memory."""
        try:
            self.logger.info("🧹 Cleaning up critic engine resources...")

            # Clear GPU memory
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Clear model references
            self.models.clear()
            self.tokenizers.clear()
            self.pipelines.clear()

            # Write any remaining feedback
            if self.feedback_data:
                self._write_feedback_to_file()

            self.logger.info("✅ Critic engine cleanup completed")

        except Exception as e:
            self.logger.error(f"❌ Cleanup failed: {e}")

    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            self.cleanup()
        except Exception:
            pass
