"""Utilities for loading the shared Mistral-7B base model with optional adapters.

These helpers try to load the adapter defined in ``AGENT_MODEL_MAP.json`` first
via :func:`agents.common.model_loader.load_transformers_with_adapter`. If that
fails (for example, when adapters have not been published yet) the helpers fall
back to loading the canonical base checkpoint so agents can still function while
training catches up.
"""

from __future__ import annotations

import os
from typing import Any

from common.observability import get_logger

try:  # pragma: no cover - transformers is an optional heavy dependency
    from transformers import AutoModelForCausalLM, AutoTokenizer
except Exception:  # pragma: no cover
    AutoModelForCausalLM = None  # type: ignore
    AutoTokenizer = None  # type: ignore

from agents.common.model_loader import (
    load_transformers_model,
    load_transformers_with_adapter,
)

logger = get_logger(__name__)

DEFAULT_BASE_MODEL_ID = os.getenv(
    "MISTRAL_BASE_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.3"
)


def load_mistral_adapter_or_base(
    agent: str,
    adapter_name: str,
    *,
    model_kwargs: dict | None = None,
    tokenizer_kwargs: dict | None = None,
) -> tuple[Any | None, Any | None]:
    """Load an agent's Mistral base + adapter, falling back to the base model.

    Returns a ``(model, tokenizer)`` tuple or ``(None, None)`` when loading fails.
    """

    adapter_errors: list[str] = []
    base_model_kwargs = {
        "device_map": "auto",
        "low_cpu_mem_usage": True,
        "trust_remote_code": True,
    }
    if model_kwargs:
        base_model_kwargs.update(model_kwargs)

    tok_kwargs = {"use_fast": True}
    if tokenizer_kwargs:
        tok_kwargs.update(tokenizer_kwargs)

    # Attempt to load the adapter first
    try:
        model, tokenizer = load_transformers_with_adapter(
            agent,
            adapter_name=adapter_name,
            model_kwargs=base_model_kwargs,
            tokenizer_kwargs=tok_kwargs,
        )
        return model, tokenizer
    except Exception as exc:  # pragma: no cover - adapter availability depends on env
        adapter_errors.append(str(exc))
        logger.debug(
            "Adapter load failed for agent=%s adapter=%s: %s", agent, adapter_name, exc
        )

    # Fall back to the base checkpoint so the agent can still operate
    if AutoModelForCausalLM is None or AutoTokenizer is None:  # pragma: no cover
        logger.warning(
            "Transformers is unavailable so the %s agent cannot load the base Mistral checkpoint",
            agent,
        )
        return None, None

    try:
        model, tokenizer = load_transformers_model(
            DEFAULT_BASE_MODEL_ID,
            agent=agent,
            model_class=AutoModelForCausalLM,
            tokenizer_class=AutoTokenizer,
            model_kwargs=base_model_kwargs,
            tokenizer_kwargs=tok_kwargs,
        )
        logger.info(
            "Loaded base Mistral checkpoint for agent=%s after adapter failure (adapter=%s)",
            agent,
            adapter_name,
        )
        return model, tokenizer
    except Exception as exc:  # pragma: no cover - depends on runtime env
        adapter_errors.append(str(exc))
        logger.warning(
            "Failed to load the base Mistral checkpoint for agent=%s (adapter errors: %s, base error: %s)",
            agent,
            "; ".join(adapter_errors),
            exc,
        )
        return None, None
