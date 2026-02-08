"""Centralized model loading helpers.

Provides small wrappers around transformers and sentence-transformers loading to
prefer canonical ModelStore paths when `MODEL_STORE_ROOT` is configured, and to
fall back to per-agent cache_dir behavior otherwise.
"""
from __future__ import annotations

import os
from pathlib import Path

from common.observability import get_logger

logger = get_logger(__name__)


def _resolve_model_store_path(agent: str | None, model_id: str | None = None) -> Path | None:
    root = os.environ.get("MODEL_STORE_ROOT")
    if not root or not agent:
        return None
    try:
        from agents.common.model_store import ModelStore
        ms = ModelStore(Path(root))
        cur = ms.get_current(agent)
        if cur and cur.exists():
            # If model_id is provided, look for the specific model subdirectory
            if model_id:
                # Convert model_id to the directory name format used by huggingface_hub
                # e.g., "google/bert_uncased_L-2_H-128_A-2" -> "models--google--bert_uncased_L-2_H-128_A-2"
                model_dir_name = model_id.replace("/", "--").replace("_", "_")
                model_dir_name = f"models--{model_dir_name}"
                model_path = cur / model_dir_name
                if model_path.exists():
                    # Check if there's a snapshots directory with actual model files
                    snapshots_dir = model_path / "snapshots"
                    if snapshots_dir.exists():
                        # Get the first (and typically only) snapshot directory
                        snapshot_dirs = list(snapshots_dir.iterdir())
                        if snapshot_dirs:
                            return snapshot_dirs[0]
                    # If no snapshots directory, return the model path directly
                    return model_path
            # If no model_id provided or specific model not found, return the current directory
            return cur
    except Exception:
        logger.debug("ModelStore not available or current not found for agent=%s", agent)
    return None


def load_transformers_model(
    model_id_or_path: str,
    agent: str | None = None,
    cache_dir: str | None = None,
    model_class: object | None = None,
    tokenizer_class: object | None = None,
) -> tuple[object, object]:
    """Load a transformers model + tokenizer with safe ModelStore support.

    Parameters:
    - model_id_or_path: HF id or filesystem path
    - agent: optional agent name to resolve ModelStore current path
    - cache_dir: optional cache_dir passed to from_pretrained
    - model_class: optional class to instantiate the model (e.g. AutoModelForCausalLM)
    - tokenizer_class: optional class to instantiate tokenizer/processor (e.g. AutoTokenizer)

    Returns (model, tokenizer/processor). If `MODEL_STORE_ROOT` is configured and a
    current model exists for `agent`, that path is used. Otherwise, cache_dir
    (if provided) or model_id_or_path is used with from_pretrained.
    """
    try:
        from transformers import AutoModel, AutoTokenizer
    except Exception as e:
        raise ImportError("transformers is required to load models") from e

    ModelClass = model_class or AutoModel
    TokenizerClass = tokenizer_class or AutoTokenizer

    # Prefer model store canonical path when configured
    ms_path = _resolve_model_store_path(agent, model_id_or_path)
    strict = os.environ.get("STRICT_MODEL_STORE") == "1"
    if ms_path:
        try:
            model = ModelClass.from_pretrained(str(ms_path))
            tokenizer = TokenizerClass.from_pretrained(str(ms_path))
            return model, tokenizer
        except Exception:
            logger.warning("Failed to load model from ModelStore path %s, falling back", ms_path)
            if strict:
                raise RuntimeError(f"STRICT_MODEL_STORE=1 but failed to load model for agent={agent} from {ms_path}")

    # Fallback to supplied cache_dir or model_id_or_path
    load_kwargs = {}
    if cache_dir:
        load_kwargs['cache_dir'] = cache_dir

    # If model_id_or_path is a filesystem path, transformers will load from there.
    model = ModelClass.from_pretrained(model_id_or_path, **load_kwargs)
    tokenizer = TokenizerClass.from_pretrained(model_id_or_path, **load_kwargs)
    return model, tokenizer


def load_sentence_transformer(model_name: str, agent: str | None = None, cache_folder: str | None = None):
    """Load a SentenceTransformer instance preferring ModelStore when configured."""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as e:
        raise ImportError("sentence-transformers is required") from e

    ms_path = _resolve_model_store_path(agent, model_name)
    strict = os.environ.get("STRICT_MODEL_STORE") == "1"
    if ms_path:
        try:
            return SentenceTransformer(str(ms_path))
        except Exception:
            logger.warning("Failed to load SentenceTransformer from ModelStore %s", ms_path)
            if strict:
                raise RuntimeError(f"STRICT_MODEL_STORE=1 but failed to load SentenceTransformer for agent={agent} from {ms_path}")

    if cache_folder:
        return SentenceTransformer(model_name, cache_folder=cache_folder)
    return SentenceTransformer(model_name)
