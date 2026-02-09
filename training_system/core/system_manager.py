"""
System-Wide Online Training Integration
Comprehensive "on the fly" training system for all V2 agents

This module integrates the online training coordinator with all V2 agents:
- Scout V2: 5 AI models (news classification, quality, sentiment, bias, visual)
- Analyst V2: spaCy NER + BERT fallback for entity extraction
- Critic V2: NLTK + pattern recognition for logical analysis
- Fact Checker V2: 5 AI models (fact verification, credibility, contradictions, evidence, claims)
- Future V2 agents: Synthesizer, Chief Editor, Memory, Dashboard

Features:
- Automatic training data collection during normal operations
- User correction integration with immediate high-priority updates
- Performance monitoring and automatic rollback
- Training status dashboard and admin controls
"""

from dataclasses import asdict
from datetime import timezone, datetime
from typing import Any

from common.observability import get_logger

# Import the core training coordinator
from .training_coordinator import (
    add_training_feedback,
    add_user_correction,
    get_online_training_status,
    get_training_coordinator,
    initialize_online_training,
)

logger = get_logger(__name__)


class SystemWideTrainingManager:
    """
    Manages online training across all V2 agents in the JustNews system
    """

    def __init__(self):
        """Initialize system-wide training management"""
        self.coordinator = get_training_coordinator()
        self.agent_configs = {
            "scout": {
                "update_threshold": 40,
                "models": [
                    "news_classification",
                    "quality_assessment",
                    "sentiment_analysis",
                    "bias_detection",
                    "visual_analysis",
                ],
                "tasks": [
                    "news_classification",
                    "quality_assessment",
                    "sentiment",
                    "bias",
                    "visual_content",
                ],
            },
            "analyst": {
                "update_threshold": 35,
                "models": ["spacy_ner", "bert_ner_fallback"],
                "tasks": [
                    "entity_extraction",
                    "numerical_analysis",
                    "statistical_analysis",
                ],
            },
            "critic": {
                "update_threshold": 25,
                "models": ["nltk_patterns", "logical_analysis"],
                "tasks": [
                    "logical_fallacy",
                    "argument_structure",
                    "editorial_consistency",
                ],
            },
            "fact_checker": {
                "update_threshold": 30,
                "models": [
                    "distilbert_fact_verification",
                    "roberta_credibility",
                    "bert_contradiction",
                    "sentence_transformers_evidence",
                    "spacy_claims",
                ],
                "tasks": [
                    "fact_verification",
                    "credibility_assessment",
                    "contradiction_detection",
                    "evidence_retrieval",
                    "claim_extraction",
                ],
            },
            "synthesizer": {
                "update_threshold": 45,
                "models": [
                    "bertopic_modeling",
                    "bart_summarization",
                    "bert_trends",
                    "sentence_similarity",
                    "t5_synthesis",
                ],
                "tasks": [
                    "topic_modeling",
                    "summarization",
                    "trend_analysis",
                    "cross_reference",
                    "editorial_synthesis",
                ],
            },
            "chief_editor": {
                "update_threshold": 20,
                "models": [
                    "bert_task_classification",
                    "roberta_quality_assurance",
                    "bert_urgency",
                    "distilbert_decisions",
                    "performance_monitoring",
                ],
                "tasks": [
                    "workflow_routing",
                    "quality_assurance",
                    "deadline_management",
                    "editorial_decisions",
                    "system_optimization",
                ],
            },
            "memory": {
                "update_threshold": 50,
                "models": [
                    "semantic_search_ensemble",
                    "knowledge_graph_construction",
                    "temporal_embeddings",
                    "fact_caching",
                    "deduplication",
                ],
                "tasks": [
                    "semantic_search",
                    "knowledge_graph",
                    "temporal_retrieval",
                    "fact_caching",
                    "content_deduplication",
                ],
            },
        }

        logger.info("🎯 System-Wide Training Manager initialized")
        logger.info(f"   📊 Managing {len(self.agent_configs)} agents")
        logger.info(
            f"   🤖 Total models: {sum(len(config['models']) for config in self.agent_configs.values())}"
        )

    def collect_agent_prediction(
        self,
        agent_name: str,
        task_type: str,
        input_text: str,
        prediction: Any,
        confidence: float,
        ground_truth: Any = None,
        source_url: str = "",
    ) -> None:
        """
        Collect prediction data from agents for training

        This should be called by agents after making predictions
        """
        try:
            if not self.coordinator:
                return

            # If we have ground truth, use it; otherwise use prediction (will be corrected by user feedback)
            actual_output = ground_truth if ground_truth is not None else prediction

            # Add to training system
            add_training_feedback(
                agent_name=agent_name,
                task_type=task_type,
                input_text=input_text,
                predicted_output=prediction,
                actual_output=actual_output,
                confidence=confidence,
            )

            # Log for monitoring
            logger.debug(
                f"📊 Prediction collected: {agent_name}/{task_type} (confidence: {confidence:.3f})"
            )

        except Exception as e:
            logger.error(f"Failed to collect prediction from {agent_name}: {e}")

    def submit_user_correction(
        self,
        agent_name: str,
        task_type: str,
        input_text: str,
        incorrect_output: Any,
        correct_output: Any,
        priority: int = 2,
        explanation: str = "",
    ) -> dict[str, Any]:
        """
        Submit user correction for immediate model improvement

        Args:
            agent_name: Name of the agent being corrected
            task_type: Type of task being corrected
            input_text: The input that was incorrectly processed
            incorrect_output: What the model predicted
            correct_output: What the correct output should be
            priority: Correction priority (0=low, 1=medium, 2=high, 3=critical)
            explanation: Optional explanation of the correction

        Returns:
            Confirmation of correction submission
        """
        try:
            add_user_correction(
                agent_name=agent_name,
                task_type=task_type,
                input_text=input_text,
                incorrect_output=incorrect_output,
                correct_output=correct_output,
                priority=priority,
            )

            result = {
                "correction_submitted": True,
                "agent_name": agent_name,
                "task_type": task_type,
                "incorrect_output": str(incorrect_output),
                "correct_output": str(correct_output),
                "priority": priority,
                "explanation": explanation,
                "immediate_update": priority >= 2,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                f"📝 User correction submitted: {agent_name}/{task_type} "
                f"(Priority: {priority}, Immediate: {priority >= 2})"
            )

            return result

        except Exception as e:
            logger.error(f"Failed to submit user correction: {e}")
            return {"correction_submitted": False, "error": str(e)}

    def get_system_training_dashboard(self) -> dict[str, Any]:
        """
        Get comprehensive training status for all agents
        """
        try:
            base_status = get_online_training_status()

            # Add system-wide information
            dashboard = {
                "system_status": {
                    "online_training_active": base_status.get("is_training", False),
                    "total_training_examples": base_status.get("total_examples", 0),
                    "agents_managed": len(self.agent_configs),
                    "last_update": datetime.now(timezone.utc).isoformat(),
                },
                "agent_status": {},
                "model_performance": base_status.get("recent_performance", []),
                "training_configuration": {
                    "update_thresholds": {
                        agent: config["update_threshold"]
                        for agent, config in self.agent_configs.items()
                    },
                    "rollback_threshold": base_status.get("rollback_threshold", 0.05),
                    "performance_window": 100,
                },
            }

            # Add detailed status for each agent
            buffer_sizes = base_status.get("buffer_sizes", {})
            for agent_name, config in self.agent_configs.items():
                buffer_size = buffer_sizes.get(agent_name, 0)
                update_ready = buffer_size >= config["update_threshold"]

                dashboard["agent_status"][agent_name] = {
                    "buffer_size": buffer_size,
                    "update_threshold": config["update_threshold"],
                    "update_ready": update_ready,
                    "progress_percentage": min(
                        100, (buffer_size / config["update_threshold"]) * 100
                    ),
                    "models_count": len(config["models"]),
                    "supported_tasks": config["tasks"],
                }

            return dashboard

        except Exception as e:
            logger.error(f"Failed to get training dashboard: {e}")
            return {
                "system_status": {"error": str(e)},
                "agent_status": {},
                "model_performance": [],
                "training_configuration": {},
            }

    def force_agent_update(self, agent_name: str) -> dict[str, Any]:
        """
        Force immediate model update for specific agent
        """
        try:
            if not self.coordinator:
                return {
                    "update_triggered": False,
                    "error": "Training coordinator not available",
                }

            success = self.coordinator.force_update_agent(agent_name)

            result = {
                "update_triggered": success,
                "agent_name": agent_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "forced": True,
            }

            if success:
                logger.info(f"🚀 Forced model update initiated for {agent_name}")
            else:
                logger.warning(
                    f"⚠️ Failed to trigger model update for {agent_name} (system may be busy)"
                )

            return result

        except Exception as e:
            logger.error(f"Failed to force update for {agent_name}: {e}")
            return {"update_triggered": False, "error": str(e)}

    def bulk_correction_import(
        self, corrections: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Import multiple corrections in bulk (for admin use)

        Args:
            corrections: List of correction dictionaries with required fields:
                - agent_name, task_type, input_text, incorrect_output, correct_output
                - Optional: priority, explanation

        Returns:
            Summary of import results
        """
        results = {
            "total_corrections": len(corrections),
            "successfully_imported": 0,
            "failed_imports": 0,
            "errors": [],
        }

        for i, correction in enumerate(corrections):
            try:
                required_fields = [
                    "agent_name",
                    "task_type",
                    "input_text",
                    "incorrect_output",
                    "correct_output",
                ]
                if not all(field in correction for field in required_fields):
                    results["errors"].append(f"Correction {i}: Missing required fields")
                    results["failed_imports"] += 1
                    continue

                self.submit_user_correction(
                    agent_name=correction["agent_name"],
                    task_type=correction["task_type"],
                    input_text=correction["input_text"],
                    incorrect_output=correction["incorrect_output"],
                    correct_output=correction["correct_output"],
                    priority=correction.get("priority", 1),
                    explanation=correction.get("explanation", ""),
                )

                results["successfully_imported"] += 1

            except Exception as e:
                results["errors"].append(f"Correction {i}: {str(e)}")
                results["failed_imports"] += 1

        logger.info(
            f"📊 Bulk correction import completed: "
            f"{results['successfully_imported']}/{results['total_corrections']} successful"
        )

        return results

    def get_agent_performance_history(
        self, agent_name: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Get performance history for specific agent
        """
        try:
            if not self.coordinator:
                return []

            # Filter performance history for specific agent
            agent_history = [
                asdict(performance)
                for performance in self.coordinator.performance_history
                if performance.agent_name == agent_name
            ]

            # Sort by timestamp and limit
            agent_history.sort(key=lambda x: x["update_timestamp"], reverse=True)
            return agent_history[:limit]

        except Exception as e:
            logger.error(f"Failed to get performance history for {agent_name}: {e}")
            return []

    def export_training_data(
        self, agent_name: str = None, task_type: str = None
    ) -> dict[str, Any]:
        """
        Export training data for analysis (admin function)
        """
        try:
            # This would export training examples from the database
            # For now, return summary information

            export_summary = {
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "filters": {"agent_name": agent_name, "task_type": task_type},
                "data_available": True,
                "note": "Training data export functionality would be implemented here",
            }

            logger.info(
                f"📤 Training data export requested: agent={agent_name}, task={task_type}"
            )

            return export_summary

        except Exception as e:
            logger.error(f"Failed to export training data: {e}")
            return {"export_timestamp": datetime.now(timezone.utc).isoformat(), "error": str(e)}

    def process_hitl_label(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Convert a HITL label payload into a training example and enqueue it."""
        label_value = str(payload.get("label", "")).lower() or "unknown"
        candidate: dict[str, Any] = payload.get("candidate") or {}

        # Ensure coordinator exists before attempting to enqueue
        if self.coordinator is None:
            self.coordinator = (
                get_training_coordinator() or initialize_online_training()
            )

        if self.coordinator is None:
            raise RuntimeError("Training coordinator is not initialized")

        # agent_name = "scout" (Deprecated)
        agent_name = "fact_checker"  # Defaulting to fact_checker as crawler is not a training target
        task_type = "news_classification"

        text_candidates = [
            candidate.get("extracted_text"),
            candidate.get("extracted_title"),
            payload.get("cleaned_text"),
        ]
        input_text = next((txt for txt in text_candidates if txt), None)
        if not input_text:
            url = candidate.get("url") or ""
            input_text = f"Candidate {candidate.get('id', payload.get('candidate_id', 'unknown'))} {url}".strip()

        uncertainty_map = {
            "valid_news": 0.1,
            "messy_news": 0.25,
            "not_news": 0.45,
        }
        uncertainty_score = uncertainty_map.get(label_value, 0.3)

        treat_as_valid = bool(payload.get("treat_as_valid"))
        needs_cleanup = bool(payload.get("needs_cleanup"))
        qa_sampled = bool(payload.get("qa_sampled"))

        importance_score = 0.6
        if treat_as_valid:
            importance_score = 0.85
        if needs_cleanup:
            importance_score = max(importance_score, 0.95)
        if qa_sampled:
            importance_score = max(importance_score, 0.9)

        priority = 0
        if needs_cleanup:
            priority = 2
        elif treat_as_valid:
            priority = 1

        expected_output: dict[str, Any] = {
            "label": label_value,
            "needs_cleanup": needs_cleanup,
            "treat_as_valid": treat_as_valid,
            "qa_sampled": qa_sampled,
            "candidate_id": payload.get("candidate_id"),
            "label_id": payload.get("label_id"),
        }

        self.coordinator.add_training_example(
            agent_name=agent_name,
            task_type=task_type,
            input_text=input_text,
            expected_output=expected_output,
            uncertainty_score=uncertainty_score,
            importance_score=importance_score,
            source_url=candidate.get("url") or "",
            user_feedback=f"HITL label: {label_value}",
            correction_priority=priority,
        )

        buffer = self.coordinator.training_buffers.get(agent_name)
        buffer_size = len(buffer) if buffer is not None else 0

        logger.info(
            "📥 HITL label processed for training: candidate=%s label=%s priority=%s",
            payload.get("candidate_id"),
            label_value,
            priority,
        )

        return {
            "agent_name": agent_name,
            "task_type": task_type,
            "label": label_value,
            "treat_as_valid": treat_as_valid,
            "needs_cleanup": needs_cleanup,
            "qa_sampled": qa_sampled,
            "buffer_size": buffer_size,
        }


# Global system-wide training manager
_training_manager = None


def get_system_training_manager() -> SystemWideTrainingManager:
    """Get or create the global system training manager"""
    global _training_manager

    if _training_manager is None:
        _training_manager = SystemWideTrainingManager()
        logger.info("🎓 System-Wide Training Manager created")

    return _training_manager


# Convenience functions for easy integration
def collect_prediction(
    agent_name: str,
    task_type: str,
    input_text: str,
    prediction: Any,
    confidence: float,
    ground_truth: Any = None,
    source_url: str = "",
) -> None:
    """Convenience function to collect agent predictions"""
    manager = get_system_training_manager()
    manager.collect_agent_prediction(
        agent_name,
        task_type,
        input_text,
        prediction,
        confidence,
        ground_truth,
        source_url,
    )


def submit_correction(
    agent_name: str,
    task_type: str,
    input_text: str,
    incorrect_output: Any,
    correct_output: Any,
    priority: int = 2,
    explanation: str = "",
) -> dict[str, Any]:
    """Convenience function to submit user corrections"""
    manager = get_system_training_manager()
    return manager.submit_user_correction(
        agent_name,
        task_type,
        input_text,
        incorrect_output,
        correct_output,
        priority,
        explanation,
    )


def get_training_dashboard() -> dict[str, Any]:
    """Convenience function to get training dashboard"""
    manager = get_system_training_manager()
    return manager.get_system_training_dashboard()


def force_update(agent_name: str) -> dict[str, Any]:
    """Convenience function to force agent updates"""
    manager = get_system_training_manager()
    return manager.force_agent_update(agent_name)
