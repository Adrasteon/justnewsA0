"""Shared embedding model helper.

Provides a process-local cached SentenceTransformer instance to avoid repeated
model downloads / loads and reduce GPU memory churn. Callers should prefer
this helper when they need a SentenceTransformer instance.
"""

import inspect
import os
import threading
import time
import warnings
from pathlib import Path
from typing import Any

from common.observability import get_logger


def _detect_caller_agent() -> str | None:
    """Return the agent folder name (e.g. 'memory', 'synthesizer') by
    inspecting the stack. Skip internal common modules (agents/common).
    """
    try:
        stack = inspect.stack()
        # Prefer frames that reference agents/<agent>/ where <agent> != 'common'
        for fr in stack:
            fname = str(fr.filename)
            parts = fname.split(os.path.sep)
            if "agents" in parts:
                idx = parts.index("agents")
                if idx + 1 < len(parts):
                    candidate = parts[idx + 1]
                    if candidate and candidate != "common":
                        return candidate
        # Fallback: return any agent-like folder if present
        for fr in stack:
            fname = str(fr.filename)
            parts = fname.split(os.path.sep)
            if "agents" in parts:
                idx = parts.index("agents")
                if idx + 1 < len(parts):
                    return parts[idx + 1]
    except Exception:
        return None
    return None


logger = get_logger(__name__)

_MODEL_CACHE = {}
_MODEL_CACHE_LOCKS = {}
_SUPPRESSION_LOGGED = False

# GPU Manager Integration
_gpu_manager = None
_model_memory_tracking: dict[str, dict[str, Any]] = {}
_memory_tracking_lock = threading.Lock()

# Smart Pre-loading Configuration
_PRELOAD_MODELS = os.environ.get("EMBEDDING_PRELOAD_MODELS", "all-MiniLM-L6-v2").split(
    ","
)
_PRELOAD_ENABLED = (
    os.environ.get("EMBEDDING_PRELOAD_ENABLED", "false").lower() == "true"
)
_PRELOAD_THREAD: threading.Thread | None = None
_PRELOAD_COMPLETED = False


def _get_gpu_manager():
    """Lazy load GPU manager to avoid circular imports"""
    global _gpu_manager
    if _gpu_manager is None:
        try:
            from agents.common.gpu_manager_production import get_gpu_manager

            _gpu_manager = get_gpu_manager()
        except ImportError:
            # Fallback to legacy GPU manager if production version not available
            try:
                from agents.common.gpu_manager import get_gpu_manager

                _gpu_manager = get_gpu_manager()
            except ImportError:
                logger.debug("GPU manager not available, running in CPU-only mode")
                _gpu_manager = None
    return _gpu_manager


def _track_model_memory_usage(
    model_name: str,
    device_key: str,
    model_size_mb: float,
    agent_name: str | None = None,
):
    """Track memory usage for loaded models"""
    with _memory_tracking_lock:
        key = f"{model_name}_{device_key}"
        _model_memory_tracking[key] = {
            "model_name": model_name,
            "device": device_key,
            "memory_mb": model_size_mb,
            "agent": agent_name or "unknown",
            "loaded_at": time.time(),
            "access_count": 0,
        }
        logger.debug(
            f"Tracked model memory: {model_name} ({model_size_mb:.1f}MB) on {device_key}"
        )


def _get_model_memory_usage(model_name: str, device_key: str) -> float:
    """Get tracked memory usage for a model"""
    with _memory_tracking_lock:
        key = f"{model_name}_{device_key}"
        if key in _model_memory_tracking:
            _model_memory_tracking[key]["access_count"] += 1
            return _model_memory_tracking[key]["memory_mb"]
    return 0.0


def get_embedding_memory_stats() -> dict[str, Any]:
    """Get comprehensive memory usage statistics for all loaded embedding models"""
    # Note: This function is called from get_embedding_cache_info() which already holds the lock
    # So we don't acquire the lock here to avoid deadlock
    total_memory = sum(info["memory_mb"] for info in _model_memory_tracking.values())
    gpu_memory = sum(
        info["memory_mb"]
        for info in _model_memory_tracking.values()
        if "cuda" in info["device"]
    )
    cpu_memory = sum(
        info["memory_mb"]
        for info in _model_memory_tracking.values()
        if info["device"] == "cpu" or info["device"] == "auto"
    )

    return {
        "total_models": len(_model_memory_tracking),
        "total_memory_mb": total_memory,
        "gpu_memory_mb": gpu_memory,
        "cpu_memory_mb": cpu_memory,
        "models_by_agent": _group_models_by_agent(),
        "cache_hit_ratio": _calculate_cache_hit_ratio(),
    }


def _group_models_by_agent() -> dict[str, list]:
    """Group loaded models by agent for analysis"""
    agent_groups = {}
    for info in _model_memory_tracking.values():
        agent = info["agent"]
        if agent not in agent_groups:
            agent_groups[agent] = []
        agent_groups[agent].append(
            {
                "model": info["model_name"],
                "memory_mb": info["memory_mb"],
                "device": info["device"],
            }
        )
    return agent_groups


def _calculate_cache_hit_ratio() -> float:
    """Calculate cache hit ratio based on access patterns"""
    total_accesses = sum(
        info["access_count"] for info in _model_memory_tracking.values()
    )
    if total_accesses == 0:
        return 0.0
    # Cache hits are when access_count > 1 (model was reused)
    cache_hits = sum(
        max(0, info["access_count"] - 1) for info in _model_memory_tracking.values()
    )
    return cache_hits / total_accesses if total_accesses > 0 else 0.0


def _estimate_model_memory_usage(model, device_key: str) -> float:
    """Estimate memory usage of a loaded model"""
    try:
        import torch

        if hasattr(model, "_modules") and device_key.startswith("cuda"):
            # Try to get actual memory usage from PyTorch
            if torch.cuda.is_available():
                # Get memory before and after model operations to estimate
                torch.cuda.synchronize()
                initial_memory = torch.cuda.memory_allocated() / (1024 * 1024)  # MB

                # Quick forward pass to ensure model is loaded
                try:
                    with torch.no_grad():
                        # Use a small dummy input to trigger memory allocation
                        _ = model.encode(["test"])
                except RuntimeError as e:
                    logger.warning(
                        f"Failed to preload model {str(model)} on {device_key}: {e}"
                    )
                torch.cuda.synchronize()
                final_memory = torch.cuda.memory_allocated() / (1024 * 1024)  # MB
                estimated_memory = max(0, final_memory - initial_memory)

                # If estimation seems too small, use a conservative default
                if estimated_memory < 50:  # Less than 50MB seems suspicious
                    estimated_memory = 200  # Conservative estimate for embedding models

                return estimated_memory
        elif device_key == "cpu":
            # Conservative CPU memory estimate
            return 150  # MB
    except Exception as e:
        logger.debug(f"Failed to estimate model memory: {e}")

    # Fallback estimates based on model name patterns
    model_name_lower = str(model).lower()
    if "large" in model_name_lower or "xl" in model_name_lower:
        return 500  # Large models
    elif "base" in model_name_lower or "medium" in model_name_lower:
        return 300  # Base/medium models
    else:
        return 200  # Small models (default)


def get_shared_embedding_model(
    model_name: str = "all-MiniLM-L6-v2",
    cache_folder: str | None = None,
    device: object | None = None,
):
    """Return a shared SentenceTransformer instance for this process.

    Args:
        model_name: HF model id or local path.
        cache_folder: Optional cache folder passed to SentenceTransformer.
        device: Optional device spec (torch.device, 'cpu', 'cuda', 'cuda:0' or int GPU id).

    Returns:
        SentenceTransformer instance (from sentence_transformers).

    Raises:
        ImportError if sentence_transformers is not installed.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        logger.error("sentence-transformers not available: %s", e)
        raise ImportError(
            "sentence-transformers package is required to load embedding models"
        ) from e

    # Normalize cache folder: prefer explicit value, else detect agent caller and use agent-local models dir
    if cache_folder is None:
        # If caller is inside an agents/<agent>/ path, use that agent's models directory by default
        try:
            stack = inspect.stack()
            caller_agent = None
            for fr in stack:
                fname = str(fr.filename)
                parts = fname.split(os.path.sep)
                if "agents" in parts:
                    idx = parts.index("agents")
                    if idx + 1 < len(parts):
                        caller_agent = parts[idx + 1]
                        break
            if caller_agent:
                cache_folder = (
                    os.environ.get(f"{caller_agent.upper()}_MODEL_CACHE")
                    or f"./agents/{caller_agent}/models"
                )
            else:
                cache_folder = os.environ.get("MEMORY_V2_CACHE", "./models/memory_v2")
        except Exception:
            cache_folder = os.environ.get("MEMORY_V2_CACHE", "./models/memory_v2")
    # Use absolute path for cache folder to avoid cache_key mismatches
    try:
        cache_folder = str(Path(cache_folder).expanduser().resolve())
    except Exception:
        cache_folder = str(cache_folder)

    # If SAFE_MODE or FORCE_CPU is set, always run on CPU and avoid GPU manager
    safe_mode = str(os.environ.get("SAFE_MODE", "0")).lower() in ("1", "true", "yes")
    force_cpu = str(os.environ.get("FORCE_CPU", "0")).lower() in ("1", "true", "yes")

    # Normalize device key for caching; if device is None, auto-detect (unless safe/force cpu)
    device_key = None
    try:
        import torch

        if device is None:
            if safe_mode or force_cpu:
                device = torch.device("cpu")
            else:
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        if isinstance(device, torch.device):
            device_key = str(device)
        elif isinstance(device, int):
            device_key = f"cuda:{device}"
        else:
            device_key = str(device)
    except Exception:
        # torch not available or other error; use string representation
        device_key = str(device) if device is not None else "auto"

    cache_key: tuple[str, str, str] = (model_name, cache_folder or "", device_key)

    # Ensure there's a lock per cache key to avoid concurrent duplicate loads
    lock = _MODEL_CACHE_LOCKS.get(cache_key)
    if lock is None:
        lock = threading.Lock()
        _MODEL_CACHE_LOCKS[cache_key] = lock

    with lock:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]

    # Ensure local model files exist under the agent cache when cache_folder is provided.
    # This guarantees agents write to their own ./agents/<agent>/models dirs.
    caller_agent = _detect_caller_agent()
    logger.info(
        "Loading shared embedding model: %s (cache=%s) device=%s agent=%s",
        model_name,
        cache_folder,
        device_key,
        caller_agent or "unknown",
    )

    # Skip GPU allocation entirely in safe/force CPU mode
    gpu_allocation = None
    if (
        (not safe_mode and not force_cpu)
        and device_key.startswith("cuda")
        and _get_gpu_manager() is not None
    ):
        try:
            gpu_manager = _get_gpu_manager()
            # Request GPU allocation for embedding model (typically smaller models)
            allocation_result = gpu_manager.request_gpu_allocation(
                agent_name=f"embedding_{caller_agent or 'unknown'}",
                requested_memory_gb=1.0,  # Conservative estimate for embedding models
                preferred_device=int(device_key.split(":")[1])
                if ":" in device_key
                else None,
                model_type="embedding",  # Specify model type for optimal batch sizing
            )

            if allocation_result["status"] == "allocated":
                gpu_allocation = allocation_result
                logger.debug(f"GPU allocated for embedding model: {allocation_result}")
            else:
                logger.warning(
                    f"GPU allocation failed for embedding model: {allocation_result}"
                )
                # Fall back to CPU
                device = torch.device("cpu")
                device_key = "cpu"
        except Exception as e:
            logger.warning(f"GPU manager integration failed: {e}, falling back to CPU")
            device = torch.device("cpu")
            device_key = "cpu"

    model = None

    # If an external canonical model store is configured, prefer loading the
    # agent's current model from the model store. This allows trainers to
    # publish versioned models and agents to load the canonical per-agent copy.
    model_store_root = os.environ.get("MODEL_STORE_ROOT")
    # Respect STRICT_MODEL_STORE when set to '1','true' or 'yes' (case-insensitive)
    strict_store = str(os.environ.get("STRICT_MODEL_STORE", "0")).lower() in (
        "1",
        "true",
        "yes",
    )
    if model_store_root:
        try:
            # local import to avoid adding dependency at module import time
            from agents.common.model_store import ModelStore

            # attempt to detect caller agent from stack (skip agents/common)
            caller_agent = _detect_caller_agent()

            if caller_agent:
                ms = ModelStore(Path(model_store_root))
                cur = ms.get_current(caller_agent)
                if cur and cur.exists():
                    # ModelStore returns the version directory (e.g. .../memory/v1) which
                    # may contain one or more model subfolders (for example when the
                    # HF snapshot format is used). Try to locate a sensible model
                    # directory inside `cur` that SentenceTransformer can load.
                    try:
                        candidate = None
                        # Common naming pattern used by the populate script:
                        # models--<library>--<model-id>
                        normalized = model_name.replace("/", "--")
                        expected_dir = cur / f"models--{normalized}"
                        if expected_dir.exists():
                            # Prefer an explicit snapshot folder if present
                            snaps = list(expected_dir.glob("snapshots/*"))
                            if snaps:
                                candidate = snaps[0]
                            else:
                                candidate = expected_dir

                        # If not found, try to discover any directory under `cur`
                        # that contains model artifacts (modules.json, config.json,
                        # pytorch_model.bin or model.safetensors). We search recursively
                        # but stop at the first sensible candidate.
                        if candidate is None:
                            for p in cur.rglob("*"):
                                if p.is_file() and p.name in (
                                    "modules.json",
                                    "config.json",
                                    "pytorch_model.bin",
                                    "model.safetensors",
                                ):
                                    candidate = p.parent
                                    break

                        if candidate is not None and candidate.exists():
                            try:
                                model = SentenceTransformer(str(candidate))
                                logger.info(
                                    "Loaded embedding model from ModelStore %s for agent %s (using %s)",
                                    cur,
                                    caller_agent,
                                    candidate,
                                )
                            except Exception as e:
                                logger.debug(
                                    "Failed to load SentenceTransformer from ModelStore candidate %s: %s",
                                    candidate,
                                    e,
                                )
                                model = None
                        else:
                            logger.debug(
                                "No suitable model directory found inside ModelStore path %s for agent %s",
                                cur,
                                caller_agent,
                            )
                            model = None
                    except Exception:
                        logger.debug(
                            "ModelStore branch failed; falling back to local cache/download"
                        )
                        model = None
        except Exception:
            logger.debug(
                "ModelStore not available or failed to load; falling back to local cache/download"
            )

    # If strict enforcement is requested, and we attempted to use the ModelStore
    # but did not obtain a model, fail fast rather than falling back to downloads.
    if strict_store and model is None:
        # Attempt to include agent name if available for better diagnostics
        agent_name = (
            caller_agent if ("caller_agent" in locals() and caller_agent) else "unknown"
        )
        raise RuntimeError(
            f"STRICT_MODEL_STORE is enabled but no model available in ModelStore for agent {agent_name}"
        )

    if model is None:
        if cache_folder:
            # If ensure_agent_model_exists is available, use it to guarantee a local model dir
            try:
                model_dir = ensure_agent_model_exists(model_name, cache_folder)
                model = SentenceTransformer(str(model_dir))
            except Exception:
                # Fallback: let SentenceTransformer handle download into cache_folder
                model = SentenceTransformer(model_name, cache_folder=cache_folder)
        else:
            model = SentenceTransformer(model_name)

    # Try to move to requested device if possible
    try:
        import torch

        if device is not None:
            # Accept torch.device, string, or int
            if isinstance(device, torch.device):
                target = device
            elif isinstance(device, int):
                target = torch.device(f"cuda:{device}")
            else:
                # string like 'cuda', 'cuda:0', 'cpu'
                target = torch.device(str(device))

            # Some SentenceTransformer wrappers accept .to(device)
            try:
                model = model.to(target)
            except Exception:
                # Fallback: some versions don't implement .to — ignore
                logger.debug(
                    "Could not .to() SentenceTransformer; continuing with default device"
                )
    except Exception:
        # torch might not be available — ignore device
        pass

    # Track memory usage after model is loaded
    try:
        model_memory_mb = _estimate_model_memory_usage(model, device_key)
        _track_model_memory_usage(model_name, device_key, model_memory_mb, caller_agent)
    except Exception as e:
        logger.debug(f"Failed to track model memory usage: {e}")

    # Wrap the SentenceTransformer to suppress known FutureWarnings from upstream
    # This suppression is controlled by the EMBEDDING_SUPPRESS_WARNINGS env var
    # so we can disable it for testing or while upgrading dependencies.
    # TODO: Remove suppression entirely after upstream libraries are updated.
    class _SentenceTransformerWrapper:
        """Proxy that delegates to a SentenceTransformer but filters noisy FutureWarnings

        Specifically suppresses warnings mentioning `encoder_attention_mask` which
        are emitted from some torch/transformers internals. We only filter this
        specific FutureWarning during encode() to avoid hiding other useful warnings.
        """

        def __init__(self, inner, model_key: str, gpu_allocation=None):
            self._inner = inner
            self._model_key = model_key
            self._gpu_allocation = gpu_allocation

        def encode(self, *args, **kwargs):
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    category=FutureWarning,
                    message=r".*encoder_attention_mask.*",
                )
                return self._inner.encode(*args, **kwargs)

        def __del__(self):
            """Cleanup GPU allocation when model wrapper is garbage collected"""
            if self._gpu_allocation and _get_gpu_manager() is not None:
                try:
                    gpu_manager = _get_gpu_manager()
                    agent_name = (
                        f"embedding_{self._gpu_allocation.get('agent_name', 'unknown')}"
                    )
                    gpu_manager.release_gpu_allocation(agent_name)
                    logger.debug(
                        f"Released GPU allocation for embedding model: {self._model_key}"
                    )
                except Exception as e:
                    logger.debug(
                        f"Failed to release GPU allocation during cleanup: {e}"
                    )

        def __getattr__(self, name):
            return getattr(self._inner, name)

    suppress = os.environ.get("EMBEDDING_SUPPRESS_WARNINGS", "1") != "0"
    global _SUPPRESSION_LOGGED
    if suppress:
        wrapped = _SentenceTransformerWrapper(
            model, f"{model_name}_{device_key}", gpu_allocation
        )
        # Log once that we're suppressing an upstream FutureWarning so operators can track this
        if not _SUPPRESSION_LOGGED:
            logger.info(
                "Embedding helper: suppressing known FutureWarning 'encoder_attention_mask' (EMBEDDING_SUPPRESS_WARNINGS=%s)",
                os.environ.get("EMBEDDING_SUPPRESS_WARNINGS"),
            )
            _SUPPRESSION_LOGGED = True
    else:
        # Return raw model (no suppression) for testing
        wrapped = model
    _MODEL_CACHE[cache_key] = wrapped
    return wrapped


def get_optimal_embedding_batch_size(
    model_name: str = "all-MiniLM-L6-v2", device: object | None = None
) -> int:
    """Get optimal batch size for embedding operations based on available resources"""
    try:
        gpu_manager = _get_gpu_manager()
        if gpu_manager is not None:
            # Request a small GPU allocation to get batch size recommendation
            allocation = gpu_manager.request_gpu_allocation(
                agent_name="embedding_batch_size_check",
                requested_memory_gb=1.0,
                model_type="embedding",
            )

            if allocation["status"] == "allocated":
                batch_size = allocation["batch_size"]
                # Clean up the temporary allocation
                gpu_manager.release_gpu_allocation("embedding_batch_size_check")
                return batch_size
    except Exception as e:
        logger.debug(f"Failed to get optimal batch size from GPU manager: {e}")

    # Fallback: conservative defaults based on device
    if device is not None and str(device).startswith("cuda"):
        return 16  # GPU default
    else:
        return 4  # CPU default


def get_embedding_performance_config(
    model_name: str = "all-MiniLM-L6-v2", device: object | None = None
) -> dict[str, Any]:
    """Get performance configuration for embedding operations"""
    batch_size = get_optimal_embedding_batch_size(model_name, device)

    config = {
        "batch_size": batch_size,
        "device": str(device) if device is not None else "auto",
        "model_name": model_name,
        "estimated_throughput": _estimate_embedding_throughput(batch_size, device),
    }

    return config


def _estimate_embedding_throughput(batch_size: int, device: object | None) -> float:
    """Estimate embedding throughput based on batch size and device"""
    try:
        if device is not None and str(device).startswith("cuda"):
            # GPU throughput estimates (embeddings/second)
            if batch_size >= 32:
                return 1000 * (batch_size / 16)  # Scale with batch size
            elif batch_size >= 16:
                return 800 * (batch_size / 16)
            elif batch_size >= 8:
                return 500 * (batch_size / 8)
            else:
                return 200 * batch_size
        else:
            # CPU throughput estimates
            return 50 * batch_size  # Conservative CPU estimate
    except Exception:
        return 100  # Safe fallback


def ensure_agent_model_exists(model_name: str, agent_cache_dir: str) -> str:
    """Ensure that a local copy of the model exists in agent_cache_dir.

    If the directory does not exist, this will download the model once using
    SentenceTransformer and save it into a temporary location then atomically
    move it into place. Uses a filesystem lock (flock) to avoid concurrent
    downloads across processes.

    Returns the absolute path to the local model directory.
    """
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        logger.error(
            "sentence-transformers not available for ensure_agent_model_exists: %s", e
        )
        raise

    agent_cache_dir = str(Path(agent_cache_dir).expanduser().resolve())
    model_dir = Path(agent_cache_dir) / model_name.replace("/", "_")

    # If model already exists on disk, return immediately
    if model_dir.exists() and any(model_dir.iterdir()):
        return str(model_dir)

    # Ensure parent directory exists
    Path(agent_cache_dir).mkdir(parents=True, exist_ok=True)

    lock_path = str(model_dir) + ".lock"
    # Use an OS-level file lock so multiple processes coordinate safely
    import fcntl

    tmp_dir = Path(f"{model_dir}.tmp")
    try:
        with open(lock_path, "w") as lf:
            # Block until we acquire exclusive lock
            try:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
            except Exception:
                # If flock is unsupported, fall back to in-process threading lock
                lock = _MODEL_CACHE_LOCKS.get(lock_path)
                if lock is None:
                    lock = threading.Lock()
                    _MODEL_CACHE_LOCKS[lock_path] = lock
                lock.acquire()
                try:
                    # inside fallback lock
                    if model_dir.exists() and any(model_dir.iterdir()):
                        return str(model_dir)
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(
                        "Downloading model %s into temporary dir %s",
                        model_name,
                        tmp_dir,
                    )
                    model = SentenceTransformer(model_name, cache_folder=str(tmp_dir))
                    try:
                        model.save(str(tmp_dir))
                    except Exception:
                        pass
                    if model_dir.exists():
                        import shutil

                        shutil.rmtree(model_dir)
                    tmp_dir.replace(model_dir)
                    logger.info(
                        "Model %s downloaded and saved to %s", model_name, model_dir
                    )
                    return str(model_dir)
                finally:
                    lock.release()

            # At this point we have flock on lf
            # Re-check under lock
            if model_dir.exists() and any(model_dir.iterdir()):
                return str(model_dir)

            try:
                tmp_dir.mkdir(parents=True, exist_ok=True)
                logger.info(
                    "Downloading model %s into temporary dir %s", model_name, tmp_dir
                )
                model = SentenceTransformer(model_name, cache_folder=str(tmp_dir))
                try:
                    model.save(str(tmp_dir))
                except Exception:
                    pass

                # Remove existing target if present and replace
                if model_dir.exists():
                    import shutil

                    shutil.rmtree(model_dir)
                tmp_dir.replace(model_dir)
                logger.info(
                    "Model %s downloaded and saved to %s", model_name, model_dir
                )
                return str(model_dir)
            except Exception as e:
                logger.error(
                    "Failed to ensure agent model exists for %s: %s", model_name, e
                )
                # Clean up tmp on failure
                try:
                    if tmp_dir.exists():
                        import shutil

                        shutil.rmtree(tmp_dir)
                except Exception:
                    pass
                raise
    except Exception as outer_e:
        logger.error(
            "ensure_agent_model_exists outer failure for %s: %s", model_name, outer_e
        )
        try:
            if tmp_dir.exists():
                import shutil

                shutil.rmtree(tmp_dir)
        except Exception:
            pass
        raise


def cleanup_embedding_cache():
    """Clean up all cached embedding models and release GPU allocations"""
    global _MODEL_CACHE, _model_memory_tracking

    logger.info("Cleaning up embedding model cache...")

    # Clear memory tracking
    with _memory_tracking_lock:
        _model_memory_tracking.clear()

    # Clear model cache (this will trigger __del__ methods for cleanup)
    models_to_cleanup = list(_MODEL_CACHE.keys())
    _MODEL_CACHE.clear()

    # Force garbage collection to trigger cleanup
    import gc
    import os

    # Skip GC during tests to prevent potential segfaults from upstream C-extensions
    # when running the full suite (likely due to mock/torch interactions).
    if os.environ.get("PYTEST_RUNNING") != "1":
        gc.collect()

    logger.info(f"Cleaned up {len(models_to_cleanup)} cached embedding models")


def get_embedding_cache_info() -> dict[str, Any]:
    """Get information about the current embedding cache state"""
    try:
        with _memory_tracking_lock:
            # Get basic cache info first
            cached_models = len(_MODEL_CACHE)
            tracked_models = len(_model_memory_tracking)
            cache_keys = list(_MODEL_CACHE.keys())

            # Get memory stats without nested lock call
            total_memory = sum(
                info["memory_mb"] for info in _model_memory_tracking.values()
            )
            gpu_memory = sum(
                info["memory_mb"]
                for info in _model_memory_tracking.values()
                if "cuda" in info["device"]
            )
            cpu_memory = sum(
                info["memory_mb"]
                for info in _model_memory_tracking.values()
                if info["device"] == "cpu" or info["device"] == "auto"
            )

            memory_stats = {
                "total_models": tracked_models,
                "total_memory_mb": total_memory,
                "gpu_memory_mb": gpu_memory,
                "cpu_memory_mb": cpu_memory,
                "models_by_agent": {},  # Skip complex grouping for now
                "cache_hit_ratio": 0.0,  # Skip calculation for now
            }

            return {
                "cached_models": cached_models,
                "tracked_models": tracked_models,
                "cache_keys": cache_keys,
                "memory_stats": memory_stats,
            }
    except Exception as e:
        logger.warning(f"Failed to get embedding cache info: {e}")
        return {
            "cached_models": 0,
            "tracked_models": 0,
            "cache_keys": [],
            "memory_stats": {
                "total_models": 0,
                "total_memory_mb": 0,
                "gpu_memory_mb": 0,
                "cpu_memory_mb": 0,
                "models_by_agent": {},
                "cache_hit_ratio": 0.0,
            },
        }


def _preload_models_background():
    """Background function to preload commonly used models"""
    global _PRELOAD_COMPLETED

    try:
        logger.info(f"Starting background preloading of models: {_PRELOAD_MODELS}")

        for model_name in _PRELOAD_MODELS:
            model_name = model_name.strip()
            if not model_name:
                continue

            try:
                logger.info(f"Preloading model: {model_name}")
                # Preload with CPU to avoid GPU contention during startup
                _ = get_shared_embedding_model(model_name, device="cpu")
                logger.info(f"✅ Successfully preloaded: {model_name}")
            except Exception as e:
                logger.warning(f"Failed to preload model {model_name}: {e}")

        logger.info("Background model preloading completed")
        _PRELOAD_COMPLETED = True

    except Exception as e:
        logger.error(f"Background preloading failed: {e}")
        _PRELOAD_COMPLETED = True  # Mark as completed even on failure


def start_embedding_preloading():
    """Start background preloading of commonly used embedding models"""
    global _PRELOAD_THREAD, _PRELOAD_COMPLETED

    if not _PRELOAD_ENABLED:
        logger.debug("Embedding preloading is disabled")
        return

    if _PRELOAD_THREAD is not None and _PRELOAD_THREAD.is_alive():
        logger.debug("Preloading already in progress")
        return

    if _PRELOAD_COMPLETED:
        logger.debug("Preloading already completed")
        return

    logger.info("Starting embedding model preloading...")
    _PRELOAD_THREAD = threading.Thread(
        target=_preload_models_background, name="embedding-preloader", daemon=True
    )
    _PRELOAD_THREAD.start()


def wait_for_preloading(timeout: float = 30.0) -> bool:
    """Wait for preloading to complete with timeout"""
    global _PRELOAD_THREAD, _PRELOAD_COMPLETED

    if not _PRELOAD_ENABLED:
        return True

    if _PRELOAD_COMPLETED:
        return True

    if _PRELOAD_THREAD is None:
        return False

    logger.info(f"Waiting for model preloading to complete (timeout: {timeout}s)...")
    _PRELOAD_THREAD.join(timeout=timeout)

    if _PRELOAD_THREAD.is_alive():
        logger.warning("Preloading did not complete within timeout")
        return False

    return _PRELOAD_COMPLETED


def get_preloading_status() -> dict[str, Any]:
    """Get the current preloading status"""
    global _PRELOAD_THREAD, _PRELOAD_COMPLETED

    return {
        "enabled": _PRELOAD_ENABLED,
        "models": _PRELOAD_MODELS,
        "completed": _PRELOAD_COMPLETED,
        "in_progress": _PRELOAD_THREAD is not None and _PRELOAD_THREAD.is_alive(),
        "thread_alive": _PRELOAD_THREAD.is_alive() if _PRELOAD_THREAD else False,
    }
