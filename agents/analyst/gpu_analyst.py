"""
GPU Analyst - Simplified GPU Acceleration Module

This module provides GPU-accelerated sentiment and bias analysis capabilities
for the Analyst agent, with production-ready memory management and fallbacks.

Features:
- GPU-accelerated sentiment analysis using RoBERTa model
- GPU-accelerated bias detection using Toxic-BERT model
- Production GPU orchestrator integration
- Memory circuit breaker for safety
- CPU fallbacks when GPU unavailable

All functions include robust error handling and comprehensive logging.
"""

import time

from common.observability import get_logger

logger = get_logger(__name__)

# Dependency detection
try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

try:
    from transformers import pipeline

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    pipeline = None
    TRANSFORMERS_AVAILABLE = False

try:
    from agents.common.gpu_orchestrator_client import GPUOrchestratorClient

    ORCHESTRATOR_AVAILABLE = True
except ImportError:
    GPUOrchestratorClient = None
    ORCHESTRATOR_AVAILABLE = False

try:
    from agents.common.gpu_manager import release_agent_gpu, request_agent_gpu

    PRODUCTION_GPU_AVAILABLE = True
except ImportError:
    PRODUCTION_GPU_AVAILABLE = False


class GPUAcceleratedAnalyst:
    """
    GPU-accelerated analyst for sentiment and bias analysis.

    This class provides production-ready GPU acceleration with:
    - GPU orchestrator integration for safe resource allocation
    - Memory circuit breaker for preventing out-of-memory errors
    - CPU fallbacks when GPU unavailable
    - Comprehensive error handling and logging
    """

    def __init__(self):
        self.gpu_available = False
        self.models_loaded = False
        self.gpu_allocated = False
        self.gpu_device = -1
        self.gpu_memory_gb = 2.0  # Analyst needs ~2GB for models
        self.memory_circuit_breaker = False
        self.memory_threshold_gb = 1.0

        self.sentiment_analyzer = None
        self.bias_detector = None

        self.performance_stats = {
            "total_requests": 0,
            "gpu_requests": 0,
            "fallback_requests": 0,
            "total_time": 0.0,
            "average_time": 0.0,
        }

        logger.info("🚀 Initializing GPU-Accelerated Analyst")

        # Check GPU availability and orchestrator decision
        orchestrator_allows_gpu = self._check_orchestrator_decision()

        if orchestrator_allows_gpu:
            self._initialize_gpu_allocation()
            self._initialize_gpu_models()
        else:
            logger.info("🛑 GPU initialization skipped - using CPU fallbacks")

    def _check_orchestrator_decision(self) -> bool:
        """Check if orchestrator allows GPU usage."""
        if not ORCHESTRATOR_AVAILABLE:
            logger.info("GPU orchestrator not available - defaulting to CPU")
            return False

        try:
            client = GPUOrchestratorClient()
            decision = client.cpu_fallback_decision()
            allows_gpu = bool(decision.get("use_gpu", False))
            logger.info(f"🔐 Orchestrator decision: use_gpu={allows_gpu}")
            return allows_gpu
        except Exception as e:
            logger.warning(f"GPU orchestrator decision failed: {e}")
            return False

    def _initialize_gpu_allocation(self):
        """Initialize GPU allocation through production manager."""
        try:
            if (
                PRODUCTION_GPU_AVAILABLE
                and TORCH_AVAILABLE
                and torch.cuda.is_available()
            ):
                allocation = request_agent_gpu("analyst", self.gpu_memory_gb)
                if (
                    isinstance(allocation, dict)
                    and allocation.get("status") == "allocated"
                ):
                    self.gpu_allocated = True
                    self.gpu_device = allocation.get("gpu_device", 0)
                    self.gpu_memory_gb = allocation.get(
                        "allocated_memory_gb", self.gpu_memory_gb
                    )
                    logger.info(
                        f"✅ GPU allocated: {self.gpu_memory_gb}GB on device {self.gpu_device}"
                    )
                else:
                    logger.warning(f"⚠️ GPU allocation failed: {allocation}")
                    self.gpu_device = 0
            else:
                self.gpu_device = (
                    0 if (TORCH_AVAILABLE and torch.cuda.is_available()) else -1
                )
        except Exception as e:
            logger.error(f"❌ GPU allocation failed: {e}")
            self.gpu_device = -1

    def _initialize_gpu_models(self):
        """Initialize GPU-accelerated models."""
        try:
            if not (
                TORCH_AVAILABLE
                and TRANSFORMERS_AVAILABLE
                and pipeline
                and self.gpu_device >= 0
            ):
                logger.warning("⚠️ GPU dependencies not available")
                return

            # Set CUDA device
            torch.cuda.set_device(self.gpu_device)
            torch.cuda.empty_cache()

            # Load sentiment analyzer
            self.sentiment_analyzer = pipeline(
                "sentiment-analysis",
                model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                device=self.gpu_device,
                max_length=512,
                truncation=True,
                top_k=None,
            )

            # Load bias detector
            self.bias_detector = pipeline(
                "text-classification",
                model="unitary/toxic-bert",
                device=self.gpu_device,
                max_length=512,
                truncation=True,
                top_k=None,
            )

            self.models_loaded = True
            logger.info("✅ GPU models loaded successfully")

        except Exception as e:
            logger.error(f"❌ GPU model initialization failed: {e}")

    def _check_memory_circuit_breaker(self) -> bool:
        """Check GPU memory and update circuit breaker."""
        if not (TORCH_AVAILABLE and torch.cuda.is_available()):
            return False

        try:
            memory_info = torch.cuda.mem_get_info(self.gpu_device)
            free_memory_gb = memory_info[0] / (1024**3)

            if free_memory_gb < self.memory_threshold_gb:
                if not self.memory_circuit_breaker:
                    logger.warning(
                        f"🔴 Memory circuit breaker activated: {free_memory_gb:.2f}GB free"
                    )
                self.memory_circuit_breaker = True
                return False
            else:
                if self.memory_circuit_breaker:
                    logger.info(
                        f"🟢 Memory circuit breaker reset: {free_memory_gb:.2f}GB free"
                    )
                self.memory_circuit_breaker = False
                return True

        except Exception as e:
            logger.error(f"Memory check failed: {e}")
            self.memory_circuit_breaker = True
            return False

    def score_sentiment_gpu(self, text: str) -> float | None:
        """
        GPU-accelerated sentiment scoring.

        Args:
            text: Text to analyze for sentiment

        Returns:
            Sentiment score (0.0-1.0) or None if GPU unavailable
        """
        if not self.models_loaded or not self.sentiment_analyzer:
            return None

        if not self._check_memory_circuit_breaker():
            return None

        start_time = time.time()
        try:
            torch.cuda.set_device(self.gpu_device)

            result = self.sentiment_analyzer(text)

            # Convert to 0.0-1.0 scale
            if isinstance(result, list) and len(result) > 0:
                scores = {item["label"].lower(): item["score"] for item in result[0]}
                sentiment_score = scores.get("positive", 0.5)
            else:
                sentiment_score = 0.5

            processing_time = time.time() - start_time
            self.performance_stats["gpu_requests"] += 1
            self.performance_stats["total_time"] += processing_time

            logger.info(
                f"✅ GPU sentiment: {sentiment_score:.3f} ({processing_time:.3f}s)"
            )
            return sentiment_score

        except Exception as e:
            logger.error(f"❌ GPU sentiment failed: {e}")
            if TORCH_AVAILABLE:
                torch.cuda.empty_cache()
            return None

    def score_bias_gpu(self, text: str) -> float | None:
        """
        GPU-accelerated bias scoring.

        Args:
            text: Text to analyze for bias

        Returns:
            Bias score (0.0-1.0) or None if GPU unavailable
        """
        if not self.models_loaded or not self.bias_detector:
            return None

        if not self._check_memory_circuit_breaker():
            return None

        start_time = time.time()
        try:
            torch.cuda.set_device(self.gpu_device)

            result = self.bias_detector(text)

            # Convert toxicity to bias score
            if isinstance(result, list) and len(result) > 0:
                scores = {item["label"]: item["score"] for item in result[0]}
                bias_score = scores.get(
                    "TOXIC", max(scores.values()) if scores else 0.5
                )
            else:
                bias_score = 0.5

            processing_time = time.time() - start_time
            self.performance_stats["gpu_requests"] += 1
            self.performance_stats["total_time"] += processing_time

            logger.info(f"✅ GPU bias: {bias_score:.3f} ({processing_time:.3f}s)")
            return bias_score

        except Exception as e:
            logger.error(f"❌ GPU bias failed: {e}")
            if TORCH_AVAILABLE:
                torch.cuda.empty_cache()
            return None

    def cleanup(self):
        """Clean up GPU resources."""
        try:
            if self.gpu_allocated and PRODUCTION_GPU_AVAILABLE:
                release_agent_gpu("analyst")
                logger.info("✅ GPU allocation released")

            if TORCH_AVAILABLE:
                torch.cuda.empty_cache()

            self.sentiment_analyzer = None
            self.bias_detector = None
            self.models_loaded = False

            logger.info("🧹 GPU analyst cleaned up")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


# Global instance
_gpu_analyst = None


def get_gpu_analyst():
    """Get or create GPU analyst instance."""
    global _gpu_analyst
    if _gpu_analyst is None:
        _gpu_analyst = GPUAcceleratedAnalyst()
    return _gpu_analyst


def cleanup_gpu_analyst():
    """Clean up GPU analyst resources."""
    global _gpu_analyst
    if _gpu_analyst is not None:
        _gpu_analyst.cleanup()
        _gpu_analyst = None
