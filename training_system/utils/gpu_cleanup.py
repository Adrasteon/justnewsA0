"""
GPU Cleanup Utilities for PyTorch Models

Helpers to manage, cleanup and safely unload PyTorch models from GPU memory.
This module provides a context manager and a global registry so callers can
ensure models are moved to CPU and deleted during shutdown or on signal.
"""

import atexit
import gc
import signal
import sys
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


class GPUModelManager:
    """
    Context manager for safe GPU model loading and cleanup
    Prevents core dumps by ensuring proper cleanup order
    """

    def __init__(self):
        """Initialize GPU model manager"""
        self._models = {}  # Dictionary to store registered models
        self._cleanup_registered = False
        self._signal_handlers_set = False

    def register_model(self, name: str, model: Any) -> None:
        """Register a model or pipeline for cleanup"""
        if model is not None:
            self._models[name] = model
            self.setup_cleanup_handlers()
            logger.debug(f"📝 Registered model: {name}")

    def register_model_legacy(self, model: Any) -> None:
        """Register a model (legacy single-parameter version)"""
        if model is not None:
            model_id = id(model)
            self._models[f"model_{model_id}"] = model
            self.setup_cleanup_handlers()
            logger.debug(f"📝 Registered model with ID: {model_id}")

    def cleanup_all_models(self) -> None:
        """Explicitly cleanup all registered models"""
        try:
            import torch

            logger.info("🧹 Starting GPU model cleanup...")

            # Clear all registered models
            for name, model in self._models.items():
                if model is not None:
                    try:
                        # Move to CPU first
                        if hasattr(model, "cpu"):
                            model.cpu()
                        # Delete the model
                        del model
                        logger.debug(f"✅ Model {name} moved to CPU and deleted")
                    except Exception as e:
                        logger.warning(f"⚠️ Error cleaning up model {name}: {e}")

            # Clear the models list
            self._models.clear()

            # Force garbage collection
            gc.collect()

            # Clear CUDA cache if available
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                logger.info("✅ CUDA cache cleared and synchronized")

            logger.info("✅ GPU model cleanup completed successfully")

        except ImportError:
            # If torch not available, skip cleanup
            logger.debug("PyTorch not available, skipping GPU cleanup")
        except Exception as e:
            logger.warning(f"⚠️ Error during GPU cleanup: {e}")

    def setup_cleanup_handlers(self) -> None:
        """Setup signal handlers and exit cleanup"""
        if self._cleanup_registered:
            return

        # Register cleanup on normal exit
        atexit.register(self.cleanup_all_models)

        # Setup signal handlers for graceful shutdown
        if not self._signal_handlers_set:

            def signal_handler(signum, frame):
                logger.info(f"🔔 Received signal {signum}, cleaning up...")
                self.cleanup_all_models()
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            self._signal_handlers_set = True

        self._cleanup_registered = True
        logger.debug("✅ GPU cleanup handlers registered")

    def __enter__(self):
        self.setup_cleanup_handlers()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_all_models()


# Global model manager instance
_global_model_manager = GPUModelManager()


def register_gpu_model(model: Any) -> None:
    """Register a GPU model for automatic cleanup"""
    _global_model_manager.register_model(model)
    _global_model_manager.setup_cleanup_handlers()


def cleanup_gpu_models() -> None:
    """Manually trigger GPU model cleanup"""
    _global_model_manager.cleanup_all_models()


def safe_gpu_context():
    """Context manager for safe GPU operations"""
    return _global_model_manager


def force_clean_exit() -> None:
    """Force a clean exit with proper GPU cleanup"""
    logger.info("🔚 Forcing clean exit with GPU cleanup...")
    cleanup_gpu_models()

    # Additional cleanup steps
    try:
        import torch

        if torch.cuda.is_available():
            # Clear all CUDA memory
            torch.cuda.empty_cache()
            # Reset CUDA context
            torch.cuda.reset_peak_memory_stats()
            logger.info("✅ CUDA context reset completed")
    except Exception as e:
        logger.warning(f"⚠️ Error during CUDA context reset: {e}")

    # Force garbage collection one more time
    gc.collect()

    logger.info("✅ Clean exit preparation completed")


class SafeModelLoader:
    """
    Context manager for loading models safely with automatic cleanup
    """

    def __init__(self, model_loader_func, *args, **kwargs):
        self.model_loader_func = model_loader_func
        self.args = args
        self.kwargs = kwargs
        self.model = None

    def __enter__(self):
        try:
            self.model = self.model_loader_func(*self.args, **self.kwargs)
            register_gpu_model(self.model)
            return self.model
        except Exception as e:
            logger.error(f"❌ Error loading model: {e}")
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.model is not None:
            try:
                # Move to CPU before cleanup
                if hasattr(self.model, "cpu"):
                    self.model.cpu()
                del self.model
                self.model = None
                logger.debug("✅ Model cleaned up in context manager")
            except Exception as e:
                logger.warning(f"⚠️ Error cleaning up model in context: {e}")
