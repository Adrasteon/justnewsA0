"""
Chief Editor Engine - Qwen-based Editorial Workflow Engine

This module provides editorial decision-making capabilities using a single
Qwen model adapter for multiple tasks.

Key Features:
- Content quality assessment via Qwen
- Fast categorization via Qwen
- Editorial sentiment analysis via Qwen
- Commentary generation via Qwen
- Comprehensive editorial decision making with fallback behavior
"""

import os
from dataclasses import dataclass
from datetime import timezone, datetime
from enum import Enum
from typing import Any

from agents.chief_editor.model_adapter import ChiefEditorModelAdapter
from common.observability import get_logger

# Core ML Libraries with fallbacks
try:
    from transformers import pipeline

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

logger = get_logger(__name__)


class EditorialPriority(Enum):
    """Editorial priority levels"""

    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW = "review"


class WorkflowStage(Enum):
    """Editorial workflow stages"""

    INTAKE = "intake"
    ANALYSIS = "analysis"
    FACT_CHECK = "fact_check"
    SYNTHESIS = "synthesis"
    REVIEW = "review"
    PUBLISH = "publish"
    ARCHIVE = "archive"


@dataclass
class EditorialDecision:
    """Editorial decision data structure"""

    priority: EditorialPriority
    stage: WorkflowStage
    confidence: float
    reasoning: str
    next_actions: list[str]
    agent_assignments: dict[str, str]
    metadata: dict[str, Any]


@dataclass
class ChiefEditorConfig:
    """Configuration for Chief Editor Engine."""

    # Decision parameters
    quality_threshold: float = 0.7
    priority_threshold: float = 0.8
    confidence_threshold: float = 0.6

    # Performance parameters  
    max_length: int = 512
    device: str = "cpu"  # Default to CPU (inference on Qwen)


class ChiefEditorEngine:
    """
    Chief Editor Editorial Workflow Engine
    
    CURRENT Architecture (Qwen-based):
    - Content quality assessment via Qwen LLM
    - Article categorization via Qwen LLM
    - Editorial sentiment analysis via Qwen LLM
    - Commentary generation via Qwen LLM
    - No local model loading (all inference remote)
    
    Optional local embeddings remain disabled by default.
    """

    def __init__(self, config: ChiefEditorConfig | None = None):
        self.config = config or ChiefEditorConfig()
        self.device = self.config.device
        # Use shared model adapter wrapper for consistent dry-run & Qwen behavior
        self.qwen_adapter = ChiefEditorModelAdapter()

        # Model containers
        self.pipelines = {}
        self.processing_stats = {
            "total_requests": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "average_processing_time": 0.0,
        }

        # Agent capabilities for routing
        self.agent_capabilities = {
            "journalist": ["content_discovery", "quality_assessment"],
            "analyst": ["sentiment_analysis", "bias_detection"],
            "fact_checker": ["fact_verification", "credibility_assessment"],
            "synthesizer": ["content_aggregation", "summarization"],
            "critic": ["content_review", "quality_control"],
        }

        # Initialize models
        self._initialize_models()

        logger.info(f"✅ Chief Editor Engine initialized on {self.device}")

    def _initialize_models(self):
        """Initialize AI models - now minimal (Qwen only).
        
        All model loading disabled. Chief Editor uses Qwen LLM for all inference.
        Legacy model loading methods kept for reference (see comments).
        """
        try:
            # All local model loading disabled - no embeddings, BERT, T5, etc.
            # Inference routes through Qwen adapter only
            # See _load_embedding_model for status
            pass

        except Exception as e:
            logger.error(f"Error initializing models: {e}")

    # DEPRECATED MODEL LOADERS - Kept for reference, not called
    # All replaced by Qwen LLM adapter
    
    def _load_bert_quality_model(self):
        """DEPRECATED: BERT model replaced by Qwen.
        
        If re-enabling, update _initialize_models() to call this.
        See git history for original implementation.
        """
        logger.info("🚫 BERT model loading disabled - using Qwen instead")
        pass

    def _load_distilbert_category_model(self):
        """DEPRECATED: DistilBERT model replaced by Qwen.
        
        If re-enabling, update _initialize_models() to call this.
        """
        logger.info("🚫 DistilBERT model loading disabled - using Qwen instead")
        pass

    def _load_roberta_sentiment_model(self):
        """DEPRECATED: RoBERTa model replaced by Qwen.
        
        If re-enabling, update _initialize_models() to call this.
        """
        logger.info("🚫 RoBERTa model loading disabled - using Qwen instead")
        pass

    def _load_t5_commentary_model(self):
        """DEPRECATED: T5 model replaced by Qwen.
        
        If re-enabling, update _initialize_models() to call this.
        """
        logger.info("🚫 T5 model loading disabled - using Qwen instead")
        pass

    def _load_embedding_model(self):
        """Load SentenceTransformer model for embeddings (DISABLED).
        
        STATUS: DEPRECATED - Embedding model loading disabled to save GPU memory.
        
        Chief Editor inference now fully routes through Qwen LLM adapter.
        No local model loading occurs.
        
        Re-enable if needed by setting CHIEF_EDITOR_ENABLE_EMBEDDINGS=1.
        """
        if os.environ.get("CHIEF_EDITOR_ENABLE_EMBEDDINGS") == "1":
            # LEGACY CODE: Re-enable if needed
            try:
                if not SENTENCE_TRANSFORMERS_AVAILABLE:
                    logger.warning("SentenceTransformers not available - using fallback")
                    return

                self.pipelines["embeddings"] = SentenceTransformer(
                    "all-MiniLM-L6-v2"  # was self.config.embedding_model
                )
                logger.info("✅ Embedding model loaded (via environment override)")

            except Exception as e:
                logger.error(f"Error loading embeddings: {e}")
                self.pipelines["embeddings"] = None
        else:
            logger.info("🚫 Embedding model loading disabled (set CHIEF_EDITOR_ENABLE_EMBEDDINGS=1 to enable)")
            self.pipelines["embeddings"] = None

    def log_feedback(self, event: str, details: dict[str, Any]):
        """Log feedback for editorial decision tracking"""
        try:
            feedback_log = os.environ.get(
                "CHIEF_EDITOR_FEEDBACK_LOG", "./feedback_chief_editor.log"
            )
            with open(feedback_log, "a", encoding="utf-8") as f:
                timestamp = datetime.now(timezone.utc).isoformat()
                f.write(f"{timestamp}\t{event}\t{details}\n")
        except Exception as e:
            logger.error(f"Error logging feedback: {e}")

    def assess_content_quality(self, text: str) -> dict[str, Any]:
        """Assess content quality using Qwen."""
        if not self.qwen_adapter:
            return self._fallback_quality_assessment(text)
            
        result = self.qwen_adapter.perform_task("quality", text)
        if not result or not isinstance(result, dict) or "overall_quality" not in result:
             return self._fallback_quality_assessment(text)

        result["model"] = "qwen-14b"
        
        self.log_feedback(
            "assess_content_quality_qwen",
            {"quality_score": result["overall_quality"], "text_length": len(text)},
        )
        return result

    def categorize_content(self, text: str) -> dict[str, Any]:
        """Categorize content using Qwen."""
        if not self.qwen_adapter:
            return self._fallback_categorization(text)
            
        result = self.qwen_adapter.perform_task("categorize", text)
        if not result or not isinstance(result, dict) or "category" not in result:
            return self._fallback_categorization(text)

        result["model"] = "qwen-14b"
        
        self.log_feedback(
            "categorize_content_qwen",
            {"category": result["category"], "confidence": result["confidence"]},
        )
        return result

    def analyze_editorial_sentiment(self, text: str) -> dict[str, Any]:
        """Analyze editorial sentiment using Qwen."""
        if not self.qwen_adapter:
            return self._fallback_sentiment_analysis(text)
            
        result = self.qwen_adapter.perform_task("sentiment", text)
        if not result or not isinstance(result, dict) or "sentiment" not in result:
            return self._fallback_sentiment_analysis(text)

        result["model"] = "qwen-14b"
        
        self.log_feedback(
            "analyze_editorial_sentiment_qwen",
            result
        )
        return result

    def generate_editorial_commentary(
        self, text: str, context: str = "news article"
    ) -> str:
        """Generate editorial commentary using Qwen."""
        if not self.qwen_adapter:
            return self._fallback_commentary_generation(text, context)

        commentary = self.qwen_adapter.perform_task("commentary", text, context)
        if not commentary or not isinstance(commentary, str):
            # Check if it returned a dict by mistake, though perform_task handles this
            return self._fallback_commentary_generation(text, context)
            
        self.log_feedback(
            "generate_editorial_commentary_qwen",
            {
                "input_length": len(text),
                "output_length": len(commentary),
                "context": context,
            },
        )
        return commentary



    def make_editorial_decision(
        self, content: str, metadata: dict[str, Any] | None = None
    ) -> EditorialDecision:
        """Make comprehensive editorial decision using all models"""
        try:
            metadata = metadata or {}

            # Run all analyses
            quality = self.assess_content_quality(content)
            category = self.categorize_content(content)
            sentiment = self.analyze_editorial_sentiment(content)

            # Determine priority and stage
            priority = self._determine_priority(quality, category, sentiment, metadata)
            stage = self._determine_workflow_stage(quality, category, metadata)

            # Calculate confidence
            confidences = [
                quality.get("overall_quality", 0.5),
                category.get("confidence", 0.5),
                sentiment.get("confidence", 0.5),
            ]
            confidence = sum(confidences) / len(confidences)

            # Generate reasoning
            reasoning = self.generate_editorial_commentary(
                content, f"{category['category']} article"
            )

            # Determine next actions
            next_actions = self._determine_next_actions(priority, stage, quality)

            # Agent assignments
            agent_assignments = self._determine_agent_assignments(
                category["category"], stage
            )

            decision = EditorialDecision(
                priority=priority,
                stage=stage,
                confidence=confidence,
                reasoning=reasoning,
                next_actions=next_actions,
                agent_assignments=agent_assignments,
                metadata=metadata,
            )

            self._attach_qwen_review(decision, content)

            self.log_feedback(
                "make_editorial_decision",
                {
                    "priority": priority.value,
                    "stage": stage.value,
                    "confidence": confidence,
                },
            )

            return decision

        except Exception as e:
            logger.error(f"Editorial decision error: {e}")
            return self._fallback_editorial_decision(content, metadata)

    def _determine_priority(
        self, quality, category, sentiment, metadata
    ) -> EditorialPriority:
        """Determine editorial priority"""
        quality_score = quality.get("overall_quality", 0.5)
        category_confidence = category.get("confidence", 0.5)
        sentiment_confidence = sentiment.get("confidence", 0.5)

        priority_score = (
            quality_score + category_confidence + sentiment_confidence
        ) / 3

        # Check for urgency indicators
        content_text = str(
            metadata.get("title", "") + " " + metadata.get("summary", "")
        ).lower()
        urgent_keywords = ["breaking", "urgent", "alert", "emergency", "crisis"]

        if any(keyword in content_text for keyword in urgent_keywords):
            return EditorialPriority.URGENT
        elif priority_score > 0.8:
            return EditorialPriority.HIGH
        elif priority_score > 0.6:
            return EditorialPriority.MEDIUM
        elif priority_score > 0.4:
            return EditorialPriority.LOW
        else:
            return EditorialPriority.REVIEW

    def _determine_workflow_stage(self, quality, category, metadata) -> WorkflowStage:
        """Determine workflow stage"""
        quality_score = quality.get("overall_quality", 0.5)

        if metadata.get("is_new", True):
            return WorkflowStage.INTAKE
        elif metadata.get("needs_fact_check", False):
            return WorkflowStage.FACT_CHECK
        elif quality_score < 0.5:
            return WorkflowStage.REVIEW
        else:
            return WorkflowStage.ANALYSIS

    def _determine_next_actions(self, priority, stage, quality) -> list[str]:
        """Determine next actions"""
        actions = []

        if priority == EditorialPriority.URGENT:
            actions.extend(["fast_track_review", "assign_senior_editor"])

        if stage == WorkflowStage.INTAKE:
            actions.extend(["initial_classification", "route_to_analyst"])
        elif stage == WorkflowStage.FACT_CHECK:
            actions.extend(["verify_facts", "check_sources"])
        elif stage == WorkflowStage.REVIEW:
            actions.extend(["detailed_review", "quality_improvement"])

        if quality.get("overall_quality", 0.5) < 0.4:
            actions.append("quality_enhancement_required")

        return actions

    def _determine_agent_assignments(
        self, category: str, stage: WorkflowStage
    ) -> dict[str, str]:
        """Determine agent assignments based on category and stage"""
        assignments = {}

        if stage == WorkflowStage.INTAKE:
            assignments["journalist"] = "content_discovery"
        elif stage == WorkflowStage.FACT_CHECK:
            assignments["fact_checker"] = "verification"
        elif stage == WorkflowStage.ANALYSIS:
            assignments["analyst"] = "sentiment_analysis"
        elif stage == WorkflowStage.SYNTHESIS:
            assignments["synthesizer"] = "content_aggregation"

        return assignments

    def _determine_editorial_tone(self, sentiment: str, confidence: float) -> str:
        """Determine editorial tone from sentiment"""
        if confidence < 0.6:
            return "neutral"

        sentiment_lower = sentiment.lower()
        if "positive" in sentiment_lower:
            return "positive"
        elif "negative" in sentiment_lower:
            return "critical"
        else:
            return "balanced"

    # Fallback methods
    def _fallback_quality_assessment(self, text: str) -> dict[str, Any]:
        return {"overall_quality": 0.5, "assessment": "medium", "model": "fallback"}

    def _fallback_categorization(self, text: str) -> dict[str, Any]:
        return {"category": "general", "confidence": 0.5, "model": "fallback"}

    def _fallback_sentiment_analysis(self, text: str) -> dict[str, Any]:
        return {
            "sentiment": "neutral",
            "confidence": 0.5,
            "editorial_tone": "balanced",
            "model": "fallback",
        }

    def _fallback_commentary_generation(self, text: str, context: str) -> str:
        return f"Editorial review required for {context}."

    def _fallback_editorial_decision(
        self, content: str, metadata: dict[str, Any] | None
    ) -> EditorialDecision:
        return EditorialDecision(
            priority=EditorialPriority.MEDIUM,
            stage=WorkflowStage.REVIEW,
            confidence=0.5,
            reasoning="Fallback decision - manual review required",
            next_actions=["manual_review"],
            agent_assignments={"journalist": "primary"},
            metadata=metadata or {},
        )

    def _attach_qwen_review(self, decision: EditorialDecision, content: str) -> None:
        if not getattr(self, "qwen_adapter", None):
            return
        try:
            review = self.qwen_adapter.review_content(
                content, metadata=decision.metadata
            )
        except Exception as exc:
            logger.debug("Chief Editor Qwen adapter failed: %s", exc)
            return
        if review:
            decision.metadata = dict(decision.metadata)
            decision.metadata["qwen_review"] = review

    def get_model_status(self) -> dict[str, bool]:
        """Get status of active and optional legacy model paths."""
        qwen_available = bool(
            getattr(self, "qwen_adapter", None)
            and getattr(self.qwen_adapter, "enabled", False)
        )
        return {
            "qwen_adapter": qwen_available,
            "qwen_review": qwen_available,
            "legacy_embeddings": self.pipelines.get("embeddings") is not None,
        }
