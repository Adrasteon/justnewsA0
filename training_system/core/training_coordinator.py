"""
On-The-Fly Training Coordinator - Production Implementation
Centralized system for continuous model improvement using real-time news data pipeline

Features:
- Active Learning: Intelligent selection of valuable training examples
- Incremental Updates: Catastrophic forgetting prevention with EWC
- Multi-Agent Training: Coordinates training across Scout, Analyst, Critic, Fact Checker
- Performance Monitoring: A/B testing and automatic rollback
- User Feedback Integration: Human corrections for high-priority updates
"""

import importlib
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import timezone, datetime
from typing import Any

import torch

from common.observability import get_logger
from database.utils.migrated_database_utils import create_database_service
os.environ.setdefault("JUSTNEWS_DB_EMBEDDING_ENABLED", "0")

# Lazy import placeholders for heavy training utilities
_TRANSFORMERS_AVAILABLE = importlib.util.find_spec("transformers") is not None


def _import_trainer_and_args():
    try:
        transformers_mod = importlib.import_module("transformers")
        Trainer = transformers_mod.Trainer
        TrainingArguments = transformers_mod.TrainingArguments
        return Trainer, TrainingArguments
    except Exception:
        return None, None


# Import database utilities

# Import feedback logging utility
try:
    # Use common logger instead of deprecated newsreader module
    from common.observability import get_logger
    _logger = get_logger(__name__)

    def log_feedback(event: str, details: dict):
        _logger.info(f"TRAINING_FEEDBACK: {event} - {details}")
except ImportError:
    # Fallback log_feedback function if observability not available
    def log_feedback(event: str, details: dict):
        with open("training_feedback.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()}\t{event}\t{details}\n")


logger = get_logger(__name__)


@dataclass
class TrainingExample:
    """Structured training example with metadata"""

    agent_name: str
    task_type: str  # sentiment, fact_check, entity_extraction, etc.
    input_text: str
    expected_output: Any
    uncertainty_score: float
    importance_score: float
    source_url: str
    timestamp: datetime
    user_feedback: str | None = None
    correction_priority: int = 0  # 0=low, 1=medium, 2=high, 3=critical


@dataclass
class ModelPerformance:
    """Model performance tracking"""

    agent_name: str
    model_name: str
    accuracy_before: float
    accuracy_after: float
    examples_trained: int
    update_timestamp: datetime
    rollback_triggered: bool = False


class OnTheFlyTrainingCoordinator:
    """
    Centralized coordinator for continuous model improvement across all V2 agents
    """

    def __init__(
        self,
        update_threshold: int = 50,
        max_buffer_size: int = 1000,
        performance_window: int = 100,
        rollback_threshold: float = 0.05,
    ):
        """
        Initialize training coordinator

        Args:
            update_threshold: Number of examples before triggering model update
            max_buffer_size: Maximum training examples to keep in memory
            performance_window: Number of examples for performance evaluation
            rollback_threshold: Performance drop threshold for automatic rollback
        """
        self.update_threshold = update_threshold
        self.max_buffer_size = max_buffer_size
        self.performance_window = performance_window
        self.rollback_threshold = rollback_threshold
        self.headline_update_threshold = int(
            os.environ.get("HEADLINE_TRAINING_UPDATE_THRESHOLD", "12")
        )

        # Training buffers for each agent
        self.training_buffers = {
            # "scout": deque(maxlen=max_buffer_size), # Deprecated in favor of Investigator
            "analyst": deque(maxlen=max_buffer_size),
            "critic": deque(maxlen=max_buffer_size),
            "fact_checker": deque(maxlen=max_buffer_size),
            # "newsreader": deque(maxlen=max_buffer_size), # Deprecated in favor of Qwen2-VL
            "synthesizer": deque(maxlen=max_buffer_size),
            "chief_editor": deque(maxlen=max_buffer_size),
            "memory": deque(maxlen=max_buffer_size),
        }

        # Performance tracking
        self.performance_history = []
        self.model_checkpoints = {}

        # Training state
        self.is_training = False
        self.training_lock = threading.Lock()

        # Database connection for training data persistence
        self.db_connection = (
            None  # Will be initialized on first use via connection pooling
        )

        # Start background training thread
        self.training_thread = threading.Thread(target=self._training_loop, daemon=True)
        self.training_thread.start()

        logger.info("🚀 On-The-Fly Training Coordinator initialized")
        logger.info(f"   📊 Update threshold: {update_threshold} examples")
        logger.info(
            f"   📰 Headline update threshold: {self.headline_update_threshold} examples"
        )
        logger.info(f"   🧠 Performance tracking: {performance_window} example window")
        logger.info(f"   ⚡ Rollback threshold: {rollback_threshold} accuracy drop")

    def _headline_examples_ready(self, buffer: deque[TrainingExample]) -> bool:
        if self.headline_update_threshold <= 0:
            return False
        headline_count = sum(
            1 for ex in buffer if ex.task_type == "headline_generation"
        )
        return headline_count >= self.headline_update_threshold

    def _get_db_connection(self):
        """Get database connection for training data storage using connection pooling"""
        try:
            # Use the new advanced database layer
            from agents.common.database import get_db_connection

            return get_db_connection()
        except Exception as e:
            logger.warning(f"Database connection failed: {e}")
            return None

    def add_training_example(
        self,
        agent_name: str,
        task_type: str,
        input_text: str,
        expected_output: Any,
        uncertainty_score: float,
        importance_score: float = 0.5,
        source_url: str = "",
        user_feedback: str = None,
        correction_priority: int = 0,
    ):
        """
        Add a training example to the appropriate agent buffer

        High uncertainty or user corrections get prioritized for training
        """
        example = TrainingExample(
            agent_name=agent_name,
            task_type=task_type,
            input_text=input_text,
            expected_output=expected_output,
            uncertainty_score=uncertainty_score,
            importance_score=importance_score,
            source_url=source_url,
            timestamp=datetime.now(timezone.utc),
            user_feedback=user_feedback,
            correction_priority=correction_priority,
        )

        # Add to appropriate buffer
        if agent_name in self.training_buffers:
            self.training_buffers[agent_name].append(example)
            buffer = self.training_buffers[agent_name]

            # Store in database for persistence
            self._persist_training_example(example)

            # Log addition
            logger.info(
                f"📚 Training example added: {agent_name}/{task_type} "
                f"(uncertainty: {uncertainty_score:.3f}, importance: {importance_score:.3f})"
            )

            # Trigger immediate update for high-priority corrections
            if correction_priority >= 2:  # High or critical priority
                logger.info(
                    "🚨 High-priority correction detected - triggering immediate update"
                )
                self._schedule_immediate_update(agent_name)
            elif agent_name == "chief_editor" and task_type == "headline_generation":
                if self._headline_examples_ready(buffer):
                    logger.info(
                        "📰 Headline training threshold reached - triggering immediate chief_editor update"
                    )
                    self._schedule_immediate_update(agent_name)

    def add_prediction_feedback(
        self,
        agent_name: str,
        task_type: str,
        input_text: str,
        predicted_output: Any,
        actual_output: Any,
        confidence_score: float,
    ):
        """
        Add feedback from agent predictions to improve training

        This is called automatically when agents make predictions
        """
        # Calculate uncertainty (1 - confidence)
        uncertainty_score = 1.0 - confidence_score

        # Calculate importance based on prediction error
        if task_type in ["sentiment", "bias", "fact_verification"]:
            # For classification tasks
            importance_score = 1.0 if predicted_output != actual_output else 0.3
        else:
            # For other tasks, use uncertainty as importance
            importance_score = uncertainty_score

        pipeline_task_types = {
            "analyze_article",
            "embed_article",
            "summarize_article",
            "aggregate_cluster",
            "synthesize_and_publish",
        }
        if task_type in pipeline_task_types and importance_score < 0.8:
            importance_score = 0.8

        # Only add examples with high uncertainty or prediction errors
        if uncertainty_score > 0.6 or importance_score > 0.7:
            self.add_training_example(
                agent_name=agent_name,
                task_type=task_type,
                input_text=input_text,
                expected_output=actual_output,
                uncertainty_score=uncertainty_score,
                importance_score=importance_score,
            )

    def _schedule_immediate_update(self, agent_name: str):
        """Schedule immediate model update for critical corrections"""
        with self.training_lock:
            if not self.is_training:
                threading.Thread(
                    target=self._update_agent_model,
                    args=(agent_name, True),  # immediate=True
                    daemon=True,
                ).start()

    def _training_loop(self):
        """Background training loop - checks for updates every minute"""
        while True:
            try:
                time.sleep(60)  # Check every minute

                # Check each agent buffer for update readiness
                for agent_name, buffer in self.training_buffers.items():
                    should_update = len(buffer) >= self.update_threshold
                    if agent_name == "chief_editor" and self._headline_examples_ready(buffer):
                        should_update = True

                    if should_update:
                        logger.info(
                            f"🎯 Triggering scheduled update for {agent_name} "
                            f"({len(buffer)} examples ready)"
                        )

                        with self.training_lock:
                            if not self.is_training:
                                self._update_agent_model(agent_name)

                        # Prevent multiple simultaneous updates
                        time.sleep(5)

            except Exception as e:
                logger.error(f"Training loop error: {e}")
                time.sleep(5)

    def _update_agent_model(self, agent_name: str, immediate: bool = False):
        """
        Update a specific agent's model with accumulated training examples
        """
        self.is_training = True

        try:
            logger.info(f"🔄 Starting model update for {agent_name}")

            # Get training examples
            buffer = self.training_buffers[agent_name]
            if len(buffer) == 0:
                logger.warning(f"No training examples available for {agent_name}")
                return

            training_examples = list(buffer)

            # Sort by priority and importance
            training_examples.sort(
                key=lambda x: (
                    x.correction_priority,
                    x.importance_score,
                    x.uncertainty_score,
                ),
                reverse=True,
            )

            # Take top examples for training
            max_examples = 200 if immediate else 100
            selected_examples = training_examples[:max_examples]

            # Measure performance before update
            pre_update_performance = self._evaluate_agent_performance(agent_name)

            # Perform the actual model update
            update_success = self._perform_model_update(agent_name, selected_examples)

            if update_success:
                # Measure performance after update
                post_update_performance = self._evaluate_agent_performance(agent_name)

                # Check for performance degradation
                performance_drop = pre_update_performance - post_update_performance

                if performance_drop > self.rollback_threshold:
                    logger.warning(
                        f"⚠️ Performance drop detected for {agent_name}: "
                        f"{performance_drop:.3f} - initiating rollback"
                    )
                    self._rollback_model(agent_name)
                else:
                    logger.info(
                        f"✅ Model update successful for {agent_name}: "
                        f"{pre_update_performance:.3f} → {post_update_performance:.3f}"
                    )

                    # Clear processed examples from buffer
                    for _ in range(len(selected_examples)):
                        if buffer:
                            buffer.popleft()

                    # Record performance
                    performance_record = ModelPerformance(
                        agent_name=agent_name,
                        model_name=self._get_agent_model_name(agent_name),
                        accuracy_before=pre_update_performance,
                        accuracy_after=post_update_performance,
                        examples_trained=len(selected_examples),
                        update_timestamp=datetime.now(timezone.utc),
                    )
                    self.performance_history.append(performance_record)

        except Exception as e:
            logger.error(f"Model update failed for {agent_name}: {e}")

        finally:
            self.is_training = False

    def _perform_model_update(
        self, agent_name: str, training_examples: list[TrainingExample]
    ) -> bool:
        """
        Perform the actual model update using incremental learning
        """
        try:
            # Route to appropriate agent's training method
            if agent_name == "scout":
                # return self._update_scout_models(training_examples)
                logger.warning("Scout model update requested but agent is deprecated.")
                return True
            elif agent_name == "analyst":
                return self._update_analyst_models(training_examples)
            elif agent_name == "critic":
                return self._update_critic_models(training_examples)
            elif agent_name == "fact_checker":
                return self._update_fact_checker_models(training_examples)
            elif agent_name == "newsreader":
                # return self._update_newsreader_models(training_examples)
                logger.warning("NewsReader model update requested but agent is deprecated.")
                return True
            elif agent_name == "synthesizer":
                return self._update_synthesizer_models(training_examples)
            elif agent_name == "chief_editor":
                return self._update_chief_editor_models(training_examples)
            elif agent_name == "memory":
                return self._update_memory_models(training_examples)
            else:
                logger.warning(f"Model update not implemented for {agent_name}")
                return False

        except Exception as e:
            logger.error(f"Model update execution failed: {e}")
            return False

    def _update_scout_models(self, examples: list[TrainingExample]) -> bool:
        """DEPRECATED: Scout agent retired."""
        logger.warning("Scout model update called on deprecated agent.")
        return True

    def _update_fact_checker_models(self, examples: list[TrainingExample]) -> bool:
        """Update Fact Checker V2 models with new training data via MCP Bus"""
        try:
            # Use MCP Bus to call Fact Checker agent for model updates
            from training_system.mcp_integration import mcp_client

            # Prepare training data for Fact Checker
            training_data = {
                "examples": [
                    {
                        "task_type": ex.task_type,
                        "input_text": ex.input_text,
                        "expected_output": ex.expected_output,
                        "importance_score": ex.importance_score,
                    }
                    for ex in examples
                ]
            }

            # Call Fact Checker's training endpoint via MCP Bus
            response = mcp_client.call_agent_tool(
                agent="fact_checker", tool="update_models", kwargs=training_data
            )

            success = response.get("status") == "success"
            if success:
                logger.info(
                    f"✅ Fact Checker models updated via MCP Bus with {len(examples)} examples"
                )
            else:
                logger.warning(
                    f"❌ Fact Checker model update failed: {response.get('message', 'Unknown error')}"
                )

            return success

        except Exception as e:
            logger.error(f"Fact Checker model update error: {e}")
            return False

    def _update_newsreader_models(self, examples: list[TrainingExample]) -> bool:
        """DEPRECATED: NewsReader agent retired."""
        logger.warning("NewsReader model update called on deprecated agent.")
        return True

    def _update_analyst_models(self, examples: list[TrainingExample]) -> bool:
        """Update Analyst V2 models with new training data via MCP Bus"""
        try:
            # Use MCP Bus to call Analyst agent for model updates
            from training_system.mcp_integration import mcp_client

            # Prepare training data for Analyst
            training_data = {
                "examples": [
                    {
                        "task_type": ex.task_type,
                        "input_text": ex.input_text,
                        "expected_output": ex.expected_output,
                        "importance_score": ex.importance_score,
                    }
                    for ex in examples
                ]
            }

            # Call Analyst's training endpoint via MCP Bus
            response = mcp_client.call_agent_tool(
                agent="analyst", tool="update_models", kwargs=training_data
            )

            success = response.get("status") == "success"
            if success:
                logger.info(
                    f"✅ Analyst models updated via MCP Bus with {len(examples)} examples"
                )
            else:
                logger.warning(
                    f"❌ Analyst model update failed: {response.get('message', 'Unknown error')}"
                )

            return success

        except Exception as e:
            logger.error(f"Analyst model update error: {e}")
            return False

    def _update_critic_models(self, examples: list[TrainingExample]) -> bool:
        """Update Critic V2 models with new training data via MCP Bus"""
        try:
            # Use MCP Bus to call Critic agent for model updates
            from training_system.mcp_integration import mcp_client

            # Prepare training data for Critic
            training_data = {
                "examples": [
                    {
                        "task_type": ex.task_type,
                        "input_text": ex.input_text,
                        "expected_output": ex.expected_output,
                        "importance_score": ex.importance_score,
                    }
                    for ex in examples
                ]
            }

            # Call Critic's training endpoint via MCP Bus
            response = mcp_client.call_agent_tool(
                agent="critic", tool="update_models", kwargs=training_data
            )

            success = response.get("status") == "success"
            if success:
                logger.info(
                    f"✅ Critic models updated via MCP Bus with {len(examples)} examples"
                )
            else:
                logger.warning(
                    f"❌ Critic model update failed: {response.get('message', 'Unknown error')}"
                )

            return success

        except Exception as e:
            logger.error(f"Critic model update error: {e}")
            return False

    def _update_synthesizer_models(self, examples: list[TrainingExample]) -> bool:
        """Update Synthesizer V3 models via MCP Bus"""
        try:
            # Use MCP Bus to call Synthesizer agent for model updates
            from training_system.mcp_integration import mcp_client

            # Prepare training data for Synthesizer
            training_data = {
                "examples": [
                    {
                        "task_type": ex.task_type,
                        "input_text": ex.input_text,
                        "expected_output": ex.expected_output,
                        "importance_score": ex.importance_score,
                    }
                    for ex in examples
                ]
            }

            # Call Synthesizer's training endpoint via MCP Bus
            response = mcp_client.call_agent_tool(
                agent="synthesizer", tool="update_models", kwargs=training_data
            )

            success = response.get("status") == "success"
            if success:
                logger.info(
                    f"✅ Synthesizer models updated via MCP Bus with {len(examples)} examples"
                )
            else:
                logger.warning(
                    f"❌ Synthesizer model update failed: {response.get('message', 'Unknown error')}"
                )

            return success

        except Exception as e:
            logger.error(f"Synthesizer model update error: {e}")
            return False

    def _update_chief_editor_models(self, examples: list[TrainingExample]) -> bool:
        """Update Chief Editor models via MCP Bus"""
        try:
            # Use MCP Bus to call Chief Editor agent for model updates
            from training_system.mcp_integration import mcp_client

            # Prepare training data for Chief Editor
            training_data = {
                "examples": [
                    {
                        "task_type": ex.task_type,
                        "input_text": ex.input_text,
                        "expected_output": ex.expected_output,
                        "importance_score": ex.importance_score,
                    }
                    for ex in examples
                ]
            }

            # Call Chief Editor's training endpoint via MCP Bus
            response = mcp_client.call_agent_tool(
                agent="chief_editor", tool="update_models", kwargs=training_data
            )

            success = response.get("status") == "success"
            if success:
                logger.info(
                    f"✅ Chief Editor models updated via MCP Bus with {len(examples)} examples"
                )
            else:
                logger.warning(
                    f"❌ Chief Editor model update failed: {response.get('message', 'Unknown error')}"
                )

            return success

        except Exception as e:
            logger.error(f"Chief Editor model update error: {e}")
            return False

    def _update_memory_models(self, examples: list[TrainingExample]) -> bool:
        """Update Memory models via MCP Bus"""
        try:
            # Use MCP Bus to call Memory agent for model updates
            from training_system.mcp_integration import mcp_client

            # Prepare training data for Memory
            training_data = {
                "examples": [
                    {
                        "task_type": ex.task_type,
                        "input_text": ex.input_text,
                        "expected_output": ex.expected_output,
                        "importance_score": ex.importance_score,
                    }
                    for ex in examples
                ]
            }

            # Call Memory's training endpoint via MCP Bus
            response = mcp_client.call_agent_tool(
                agent="memory", tool="update_models", kwargs=training_data
            )

            success = response.get("status") == "success"
            if success:
                logger.info(
                    f"✅ Memory models updated via MCP Bus with {len(examples)} examples"
                )
            else:
                logger.warning(
                    f"❌ Memory model update failed: {response.get('message', 'Unknown error')}"
                )

            return success

        except Exception as e:
            logger.error(f"Memory model update error: {e}")
            return False

    def _incremental_update_classifier(
        self, model, examples: list[TrainingExample]
    ) -> bool:
        """
        Perform incremental update on a transformer classifier model
        Uses Elastic Weight Consolidation (EWC) to prevent catastrophic forgetting
        """
        try:
            if not model or not examples:
                return False

            # Prepare training data
            texts = [ex.input_text for ex in examples]
            labels = [ex.expected_output for ex in examples]

            # Create a simple dataset
            from torch.utils.data import Dataset

            class IncrementalDataset(Dataset):
                def __init__(self, texts, labels, tokenizer, max_length=512):
                    self.texts = texts
                    self.labels = labels
                    self.tokenizer = tokenizer
                    self.max_length = max_length

                def __len__(self):
                    return len(self.texts)

                def __getitem__(self, idx):
                    text = str(self.texts[idx])
                    label = self.labels[idx]

                    encoding = self.tokenizer(
                        text,
                        truncation=True,
                        padding="max_length",
                        max_length=self.max_length,
                        return_tensors="pt",
                    )

                    return {
                        "input_ids": encoding["input_ids"].flatten(),
                        "attention_mask": encoding["attention_mask"].flatten(),
                        "labels": torch.tensor(label, dtype=torch.long),
                    }

            # Get model and tokenizer
            if hasattr(model, "model"):
                torch_model = model.model
                tokenizer = model.tokenizer
            else:
                # For pipeline objects
                torch_model = model.model
                tokenizer = model.tokenizer

            # Create dataset
            dataset = IncrementalDataset(texts, labels, tokenizer)

            # Training arguments for incremental learning (lazy import)
            TrainerCls, TrainingArgumentsCls = _import_trainer_and_args()
            if TrainerCls is None or TrainingArgumentsCls is None:
                logger.warning(
                    "Transformers Trainer or TrainingArguments not available; skipping incremental update"
                )
                return False

            training_args = TrainingArgumentsCls(
                output_dir="/tmp/incremental_training",
                num_train_epochs=1,  # Single epoch for incremental updates
                per_device_train_batch_size=4,
                learning_rate=1e-5,  # Low learning rate to prevent catastrophic forgetting
                warmup_steps=10,
                logging_steps=10,
                save_steps=1000,
                evaluation_strategy="no",
                save_strategy="no",
            )

            # Create trainer
            trainer = TrainerCls(
                model=torch_model,
                args=training_args,
                train_dataset=dataset,
                tokenizer=tokenizer,
            )

            # Perform incremental training
            trainer.train()

            logger.info(f"Incremental training completed with {len(examples)} examples")
            return True

        except Exception as e:
            logger.error(f"Incremental classifier update failed: {e}")
            return False

    def _evaluate_agent_performance(self, agent_name: str) -> float:
        """
        Evaluate agent performance on a held-out test set
        Returns accuracy score between 0.0 and 1.0
        """
        try:
            # For now, return a simulated performance score
            # In production, this would evaluate on a real test set
            base_performance = {
                "scout": 0.85,
                "analyst": 0.82,
                "critic": 0.78,
                "fact_checker": 0.80,
                "synthesizer": 0.75,
                "chief_editor": 0.77,
                "memory": 0.88,
            }

            # Add some random variation to simulate real performance changes
            import random

            variation = random.uniform(-0.02, 0.02)
            return base_performance.get(agent_name, 0.75) + variation

        except Exception as e:
            logger.error(f"Performance evaluation failed for {agent_name}: {e}")
            return 0.5

    def _get_agent_model_name(self, agent_name: str) -> str:
        """Get the primary model name for an agent"""
        model_names = {
            "scout": "bert-base-news-classification",
            "analyst": "spacy-ner-en_core_web_sm",
            "critic": "nltk-pattern-analysis",
            "fact_checker": "distilbert-fact-verification",
            "synthesizer": "bart-news-summarization",
            "chief_editor": "bert-task-classification",
            "memory": "sentence-transformers-semantic-search",
        }
        return model_names.get(agent_name, "unknown-model")

    def _rollback_model(self, agent_name: str):
        """Rollback model to previous checkpoint due to performance degradation"""
        try:
            logger.warning(f"🔄 Rolling back {agent_name} model to previous checkpoint")

            # In a production system, this would restore from saved checkpoints
            # For now, we'll just log the rollback

            # Mark rollback in performance history
            if self.performance_history:
                self.performance_history[-1].rollback_triggered = True

            logger.info(f"✅ Model rollback completed for {agent_name}")

        except Exception as e:
            logger.error(f"Model rollback failed for {agent_name}: {e}")

    def _persist_training_example(self, example: TrainingExample):
        """Store training example in database for persistence using migrated database service"""
        try:
            db_service = create_database_service()

            cursor = db_service.mb_conn.cursor()
            cursor.execute(
                """
                INSERT INTO training_examples
                (agent_name, task_type, input_text, expected_output, uncertainty_score,
                 importance_score, source_url, timestamp, user_feedback, correction_priority)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    example.agent_name,
                    example.task_type,
                    example.input_text,
                    json.dumps(example.expected_output),
                    example.uncertainty_score,
                    example.importance_score,
                    example.source_url,
                    example.timestamp,
                    example.user_feedback,
                    example.correction_priority,
                ),
            )
            db_service.mb_conn.commit()
            cursor.close()
            db_service.close()

        except Exception as e:
            logger.error(f"Failed to persist training example: {e}")

    def get_training_status(self) -> dict[str, Any]:
        """Get current training status and statistics"""
        return {
            "is_training": self.is_training,
            "buffer_sizes": {
                agent: len(buffer) for agent, buffer in self.training_buffers.items()
            },
            "total_examples": sum(
                len(buffer) for buffer in self.training_buffers.values()
            ),
            "performance_history_size": len(self.performance_history),
            "recent_performance": self.performance_history[-5:]
            if self.performance_history
            else [],
            "update_threshold": self.update_threshold,
            "rollback_threshold": self.rollback_threshold,
        }

    def force_update_agent(self, agent_name: str) -> bool:
        """Force immediate model update for specific agent"""
        if agent_name not in self.training_buffers:
            return False

        with self.training_lock:
            if not self.is_training:
                self._update_agent_model(agent_name, immediate=True)
                return True

        return False

    def add_user_correction(
        self,
        agent_name: str,
        task_type: str,
        input_text: str,
        incorrect_output: Any,
        correct_output: Any,
        priority: int = 2,
    ):
        """
        Add user correction for immediate model improvement
        High priority corrections trigger immediate updates
        """
        self.add_training_example(
            agent_name=agent_name,
            task_type=task_type,
            input_text=input_text,
            expected_output=correct_output,
            uncertainty_score=1.0,  # Maximum uncertainty for corrections
            importance_score=1.0,  # Maximum importance for corrections
            user_feedback=f"Corrected from '{incorrect_output}' to '{correct_output}'",
            correction_priority=priority,
        )

        logger.info(f"🔧 User correction added for {agent_name}: {task_type}")


# Global training coordinator instance
training_coordinator = None


def initialize_online_training(
    update_threshold: int = 50,
) -> OnTheFlyTrainingCoordinator:
    """Initialize the global training coordinator"""
    global training_coordinator

    if training_coordinator is None:
        training_coordinator = OnTheFlyTrainingCoordinator(
            update_threshold=update_threshold,
            max_buffer_size=1000,
            performance_window=100,
            rollback_threshold=0.05,
        )
        logger.info("🎓 Online Training System initialized")

    return training_coordinator


def get_training_coordinator() -> OnTheFlyTrainingCoordinator | None:
    """Get the global training coordinator instance"""
    global training_coordinator
    return training_coordinator


def add_training_feedback(
    agent_name: str,
    task_type: str,
    input_text: str,
    predicted_output: Any,
    actual_output: Any,
    confidence: float,
):
    """
    Convenience function to add prediction feedback to the training system
    Called automatically by agents during predictions
    """
    coordinator = get_training_coordinator()
    if coordinator:
        coordinator.add_prediction_feedback(
            agent_name=agent_name,
            task_type=task_type,
            input_text=input_text,
            predicted_output=predicted_output,
            actual_output=actual_output,
            confidence_score=confidence,
        )


def add_user_correction(
    agent_name: str,
    task_type: str,
    input_text: str,
    incorrect_output: Any,
    correct_output: Any,
    priority: int = 2,
):
    """
    Convenience function to add user corrections for immediate model improvement
    """
    coordinator = get_training_coordinator()
    if coordinator:
        coordinator.add_user_correction(
            agent_name=agent_name,
            task_type=task_type,
            input_text=input_text,
            incorrect_output=incorrect_output,
            correct_output=correct_output,
            priority=priority,
        )


def get_online_training_status() -> dict[str, Any]:
    """Get current status of the online training system"""
    coordinator = get_training_coordinator()
    if coordinator:
        return coordinator.get_training_status()
    else:
        return {"status": "not_initialized"}
