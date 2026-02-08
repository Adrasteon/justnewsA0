"""Centralized model loading helpers.

Provides small wrappers around transformers and sentence-transformers loading to
prefer canonical ModelStore paths when `MODEL_STORE_ROOT` is configured, and to
fall back to per-agent cache_dir behavior otherwise.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


def _project_root() -> Path:
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()


@lru_cache(maxsize=1)
def _load_agent_model_map() -> dict:
    path = _project_root() / "AGENT_MODEL_MAP.json"
    if not path.exists():
        logger.debug("AGENT_MODEL_MAP.json not found at %s", path)
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        logger.warning("Failed to parse AGENT_MODEL_MAP.json: %s", exc)
        return {}


def _agent_base_entry(
    agent: str | None, adapter_name: str | None = None
) -> tuple[dict, dict] | None:
    if not agent:
        return None
    model_map = _load_agent_model_map()
    base_models = model_map.get("base_models", {})
    agents_cfg = model_map.get("agents")
    if agents_cfg is None:
        if model_map:
            agents_cfg = {k: v for k, v in model_map.items() if k != "base_models"}
        else:
            agents_cfg = {}
    agent_entries = agents_cfg.get(agent)
    if not agent_entries:
        return None
    if not isinstance(agent_entries, list):
        agent_entries = [agent_entries]

    selected: dict[str, Any] | None = None
    if adapter_name:
        for entry in agent_entries:
            if isinstance(entry, dict) and entry.get("adapter_name") == adapter_name:
                selected = entry
                break
    if selected is None:
        selected = (
            agent_entries[0] if isinstance(agent_entries, list) else agent_entries
        )

    if not isinstance(selected, dict):
        return None

    base_ref = selected.get("base_ref")
    if not base_ref:
        return None
    base_info = base_models.get(base_ref, {})
    return selected, base_info


def _resolve_version_dir(base_info: dict) -> Path | None:
    root_env = os.environ.get("MODEL_STORE_ROOT")
    if not root_env:
        return None
    root = Path(root_env)
    path_hint = base_info.get("model_store_path")
    if path_hint:
        candidate = Path(path_hint)
        if not candidate.is_absolute():
            candidate = root / path_hint
        if candidate.exists():
            return candidate
    version = base_info.get("model_store_version")
    agent = (
        base_info.get("model_store_agent") or base_info.get("agent") or "base_models"
    )
    if version:
        try:
            from agents.common.model_store import ModelStore

            store = ModelStore(root)
            candidate = store.version_path(agent, version)
            if candidate.exists():
                return candidate
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug(
                "Failed to resolve version dir for agent=%s version=%s: %s",
                agent,
                version,
                exc,
            )
    return None


def _resolve_adapter_path(agent: str, entry: dict) -> Path | None:
    root_env = os.environ.get("MODEL_STORE_ROOT")
    if not root_env:
        return None
    root = Path(root_env)
    candidates: list[Path] = []
    raw_path = entry.get("adapter_model_store_path")
    if raw_path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = root / raw_path
        candidates.append(candidate)

    version = entry.get("adapter_version")
    adapter_agent = entry.get("adapter_agent") or agent
    if version:
        try:
            from agents.common.model_store import ModelStore

            store = ModelStore(root)
            version_dir = store.version_path(adapter_agent, version)
            subdir = entry.get("adapter_subdir") or (
                f"adapters/{entry.get('adapter_name')}"
                if entry.get("adapter_name")
                else None
            )
            if subdir:
                candidates.append(version_dir / subdir)
            else:
                candidates.append(version_dir)
        except Exception as exc:  # pragma: no cover
            logger.debug(
                "Failed to resolve adapter version path for agent=%s version=%s: %s",
                adapter_agent,
                version,
                exc,
            )

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_snapshot_path(base_dir: Path, model_id: str | None) -> Path | None:
    if not base_dir.exists():
        return None
    if not model_id:
        return base_dir
    model_dir_name = f"models--{model_id.replace('/', '--')}"
    model_path = base_dir / model_dir_name
    if model_path.exists():
        snapshots_dir = model_path / "snapshots"
        if snapshots_dir.exists():
            snapshot_dirs = sorted([p for p in snapshots_dir.iterdir() if p.is_dir()])
            if snapshot_dirs:
                return snapshot_dirs[0]
        return model_path
    return base_dir


def _resolve_model_store_path(
    agent: str | None, model_id: str | None = None, adapter_name: str | None = None
) -> Path | None:
    root_env = os.environ.get("MODEL_STORE_ROOT")
    if not root_env or not agent:
        return None
    root = Path(root_env)
    base_dir: Path | None = None
    base_entry = _agent_base_entry(agent, adapter_name)
    try:
        from agents.common.model_store import ModelStore

        store = ModelStore(root)
    except Exception:
        store = None

    if base_entry:
        _, base_info = base_entry
        explicit_path = base_info.get("model_store_path")
        if explicit_path:
            candidate = root / explicit_path
            if candidate.exists():
                base_dir = candidate
        if base_dir is None:
            base_agent = base_info.get("model_store_agent") or agent
            base_version = base_info.get("model_store_version")
            if store and base_agent:
                if base_version:
                    candidate = store.version_path(base_agent, base_version)
                    if candidate.exists():
                        base_dir = candidate
                else:
                    candidate = store.get_current(base_agent)
                    if candidate:
                        base_dir = candidate

    if base_dir is None and store:
        cur = store.get_current(agent)
        if cur:
            base_dir = cur

    if base_dir is None:
        logger.debug("Failed to resolve ModelStore path for agent=%s", agent)
        return None

    return _resolve_snapshot_path(base_dir, model_id)


def load_transformers_model(
    model_id_or_path: str,
    agent: str | None = None,
    cache_dir: str | None = None,
    model_class: object | None = None,
    tokenizer_class: object | None = None,
    model_kwargs: dict | None = None,
    tokenizer_kwargs: dict | None = None,
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
            model = ModelClass.from_pretrained(str(ms_path), **(model_kwargs or {}))
            tokenizer = TokenizerClass.from_pretrained(
                str(ms_path), **(tokenizer_kwargs or {})
            )
            return model, tokenizer
        except Exception as e:
            logger.warning(
                "Failed to load model from ModelStore path %s, falling back", ms_path
            )
            if strict:
                raise RuntimeError(
                    f"STRICT_MODEL_STORE=1 but failed to load model for agent={agent} from {ms_path}"
                ) from e

    # Fallback to supplied cache_dir or model_id_or_path
    load_kwargs = dict(model_kwargs or {})
    if cache_dir:
        load_kwargs["cache_dir"] = cache_dir

    tokenizer_load_kwargs = dict(tokenizer_kwargs or {})
    if cache_dir:
        tokenizer_load_kwargs["cache_dir"] = cache_dir

    # If model_id_or_path is a filesystem path, transformers will load from there.
    model = ModelClass.from_pretrained(model_id_or_path, **load_kwargs)
    tokenizer = TokenizerClass.from_pretrained(
        model_id_or_path, **tokenizer_load_kwargs
    )
    return model, tokenizer


def load_sentence_transformer(
    model_name: str, agent: str | None = None, cache_folder: str | None = None
):
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
        except Exception as e:
            logger.warning(
                "Failed to load SentenceTransformer from ModelStore %s", ms_path
            )
            if strict:
                raise RuntimeError(
                    f"STRICT_MODEL_STORE=1 but failed to load SentenceTransformer for agent={agent} from {ms_path}"
                ) from e

    if cache_folder:
        return SentenceTransformer(model_name, cache_folder=cache_folder)
    return SentenceTransformer(model_name)


def _truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def load_transformers_with_adapter(
    agent: str,
    adapter_name: str | None = None,
    *,
    base_model_id: str | None = None,
    model_class: object | None = None,
    tokenizer_class: object | None = None,
    model_kwargs: dict | None = None,
    tokenizer_kwargs: dict | None = None,
) -> tuple[object, object]:
    """Load a causal transformers model plus adapter as defined in AGENT_MODEL_MAP.json."""

    adapter_entry = _agent_base_entry(agent, adapter_name)
    if not adapter_entry:
        raise RuntimeError(f"No AGENT_MODEL_MAP entry with adapter for agent={agent}")

    entry, base_info = adapter_entry
    resolved_adapter_name = adapter_name or entry.get("adapter_name")
    base_agent = base_info.get("model_store_agent") or agent
    base_model_identifier = base_model_id or base_info.get("hf_id")

    if not base_model_identifier:
        raise RuntimeError(f"Missing base model identifier for agent={agent}")

    dry_run_enabled = _truthy_env(os.environ.get("MODEL_STORE_DRY_RUN")) or _truthy_env(
        os.environ.get("DRY_RUN")
    )

    base_model_kwargs = {
        "device_map": "auto",
        "low_cpu_mem_usage": True,
        "trust_remote_code": True,
    }
    if model_kwargs:
        base_model_kwargs.update(model_kwargs)

    adapter_path = _resolve_adapter_path(agent, entry)
    strict = _truthy_env(os.environ.get("STRICT_MODEL_STORE"))

    if dry_run_enabled:
        base_path = _resolve_model_store_path(base_agent, base_model_identifier)
        if strict and resolved_adapter_name and adapter_path is None:
            raise RuntimeError(
                f"STRICT_MODEL_STORE=1 but adapter path missing for agent={agent} adapter={resolved_adapter_name}"
            )
        return (
            {
                "dry_run": True,
                "agent": agent,
                "base_path": str(base_path or base_model_identifier),
            },
            {
                "dry_run": True,
                "adapter_path": str(adapter_path) if adapter_path else None,
            },
        )

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except Exception as exc:
        raise ImportError("transformers is required to load adapters") from exc

    model, tokenizer = load_transformers_model(
        base_model_identifier,
        agent=base_agent,
        model_class=model_class or AutoModelForCausalLM,
        tokenizer_class=tokenizer_class or AutoTokenizer,
        model_kwargs=base_model_kwargs,
        tokenizer_kwargs=tokenizer_kwargs,
    )

    if adapter_path and adapter_path.exists():
        try:
            from peft import PeftModel  # type: ignore

            model = PeftModel.from_pretrained(model, str(adapter_path))
        except Exception as exc:
            if strict:
                raise RuntimeError(
                    f"Failed to load adapter {resolved_adapter_name} for agent={agent} from {adapter_path}"
                ) from exc
            logger.warning(
                "Adapter load failed for agent=%s adapter=%s path=%s: %s",
                agent,
                resolved_adapter_name,
                adapter_path,
                exc,
            )
    else:
        if resolved_adapter_name:
            logger.debug(
                "Adapter path not resolved for agent=%s adapter=%s",
                agent,
                resolved_adapter_name,
            )
        if strict and resolved_adapter_name:
            raise RuntimeError(
                f"STRICT_MODEL_STORE=1 but adapter path missing for agent={agent} adapter={resolved_adapter_name}"
            )

    return model, tokenizer


def get_agent_model_metadata(
    agent: str, adapter_name: str | None = None
) -> dict[str, Any] | None:
    """Return metadata describing base + adapter paths, manifest contents, etc."""

    adapter_entry = _agent_base_entry(agent, adapter_name)
    if not adapter_entry:
        return None
    entry, base_info = adapter_entry
    version_dir = _resolve_version_dir(base_info)
    manifest = None
    if version_dir:
        manifest_path = version_dir / "manifest.json"
        if manifest_path.exists():
            try:
                with manifest_path.open("r", encoding="utf-8") as fh:
                    manifest = json.load(fh)
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "Failed to read manifest for agent=%s path=%s: %s",
                    agent,
                    manifest_path,
                    exc,
                )
    adapter_path = _resolve_adapter_path(agent, entry)
    return {
        "agent": agent,
        "adapter_name": adapter_name or entry.get("adapter_name"),
        "entry": entry,
        "base_info": base_info,
        "version_dir": version_dir,
        "manifest": manifest,
        "adapter_path": adapter_path,
    }
