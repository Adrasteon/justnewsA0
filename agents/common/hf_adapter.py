from __future__ import annotations

import logging
import math
import os
import time
from contextlib import nullcontext, suppress
from typing import Any

from common.metrics import get_metrics

from .adapter_base import AdapterError, BaseAdapter
from .model_loader import load_transformers_model

logger = logging.getLogger(__name__)


def _normalize_quantization(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"int8", "8bit", "load_in_8bit"}:
        return "int8"
    if normalized in {"int4", "4bit", "load_in_4bit"}:
        return "int4"
    return None


class HFAdapter(BaseAdapter):
    """Reusable HuggingFace adapter for local/ModelStore models.

    Supports dry-run execution, optional quantization (int8/int4 via bitsandbytes),
    retries with exponential backoff, and ModelStore-aware loading.
    """

    def __init__(
        self,
        model_name: str = "gpt2",
        *,
        name: str = "hf",
        agent: str | None = None,
        cache_dir: str | None = None,
        device: str | None = None,
        quantization: str | None = None,
        trust_remote_code: bool | None = None,
        generation_kwargs: dict | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        super().__init__(name=name)
        self._name = name
        self._model_id = model_name
        self._agent = agent
        self._cache_dir = cache_dir
        self._device = device or os.environ.get("HF_DEVICE", "auto")
        env_quant = os.environ.get("HF_ADAPTER_QUANTIZATION")
        self._quantization_mode = _normalize_quantization(quantization or env_quant)
        self._trust_remote_code = bool(
            trust_remote_code
            if trust_remote_code is not None
            else os.environ.get("HF_TRUST_REMOTE_CODE") in {"1", "true", "yes"}
        )
        self._generation_defaults: dict[str, Any] = {
            "max_new_tokens": 256,
            "temperature": 0.7,
            "do_sample": False,
        }
        if generation_kwargs:
            self._generation_defaults.update(generation_kwargs)
        self._timeout = float(timeout)
        self._max_retries = int(max_retries)
        self._backoff_base = float(backoff_base)
        try:
            self._metrics = get_metrics(self._name)
        except Exception:
            self._metrics = None
        self._model = None
        self._tokenizer = None

    # ------------------------------------------------------------------
    def _quantization_kwargs(self) -> dict[str, Any]:
        if self._quantization_mode == "int8":
            return {"load_in_8bit": True}
        if self._quantization_mode == "int4":
            return {"load_in_4bit": True}
        return {}

    def _generation_kwargs(self, overrides: dict | None) -> dict[str, Any]:
        data = dict(self._generation_defaults)
        if overrides:
            data.update(overrides)
        return data

    def _prepare_inputs(self, prompt: str):
        if self._tokenizer is None:
            raise AdapterError("hf-tokenizer-missing")
        encoded = self._tokenizer(prompt, return_tensors="pt")
        target_device = (self._device or "auto").lower()
        if target_device and target_device not in {"auto", "default"}:
            with suppress(Exception):
                encoded = {
                    k: (v.to(target_device) if hasattr(v, "to") else v)
                    for k, v in encoded.items()
                }
        return encoded

    # ------------------------------------------------------------------
    def load(self, model_id: str | None = None, config: dict | None = None) -> None:
        model_identifier = model_id or config.get("model_id") if config else None
        model_identifier = model_identifier or self._model_id
        cache_dir = config.get("cache_dir") if config else None
        cache_dir = cache_dir or self._cache_dir

        if self.dry_run:
            self._model = {"dry_run": True, "model_id": model_identifier}
            self._tokenizer = {"dry_run": True}
            self.mark_loaded()
            return

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise AdapterError("transformers-required") from exc

        model_kwargs: dict[str, Any] = {
            "low_cpu_mem_usage": True,
            "trust_remote_code": self._trust_remote_code,
        }
        tokenizer_kwargs: dict[str, Any] = {}
        if cache_dir:
            model_kwargs["cache_dir"] = cache_dir
            tokenizer_kwargs["cache_dir"] = cache_dir

        if self._device and self._device.lower() == "auto":
            model_kwargs["device_map"] = "auto"
        elif self._device:
            model_kwargs["device_map"] = None

        model_kwargs.update(self._quantization_kwargs())

        try:
            model, tokenizer = load_transformers_model(
                model_identifier,
                agent=self._agent,
                cache_dir=cache_dir,
                model_class=AutoModelForCausalLM,
                tokenizer_class=AutoTokenizer,
                model_kwargs=model_kwargs,
                tokenizer_kwargs=tokenizer_kwargs,
            )
        except Exception as exc:  # pragma: no cover
            raise AdapterError(f"hf-load-failed: {exc}") from exc

        # Ensure pad token is set for generation if missing
        if (
            hasattr(tokenizer, "pad_token")
            and getattr(tokenizer, "pad_token", None) is None
        ):
            with suppress(Exception):
                tokenizer.pad_token = tokenizer.eos_token  # type: ignore[attr-defined]

        self._model = model
        self._tokenizer = tokenizer
        self.mark_loaded()

    # ------------------------------------------------------------------
    def infer(self, prompt: str, **generation_overrides: Any) -> dict:
        self.ensure_loaded()

        if self.dry_run:
            start = time.time()
            duration = time.time() - start
            if self._metrics:
                with suppress(Exception):
                    self._metrics.timing("hf_infer_latency_seconds", duration)
                    self._metrics.increment("hf_infer_success")
            return {
                "text": f"[DRYRUN-hf:{self._model_id}] Simulated response to: {prompt[:120]}",
                "raw": {"simulated": True},
                "tokens": len(prompt.split()),
                "latency": duration,
            }

        gen_kwargs = self._generation_kwargs(generation_overrides)
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            start = time.time()
            try:
                encoded = self._prepare_inputs(prompt)
                try:
                    import torch  # type: ignore
                except Exception as exc:  # pragma: no cover
                    raise AdapterError("torch-required") from exc

                inference_ctx = getattr(torch, "inference_mode", None)
                if callable(inference_ctx):
                    context_manager = inference_ctx()
                elif hasattr(torch, "no_grad"):
                    context_manager = torch.no_grad()
                else:
                    context_manager = nullcontext()
                with context_manager:
                    output = self._model.generate(**encoded, **gen_kwargs)
                duration = time.time() - start
                text = self._tokenizer.decode(output[0], skip_special_tokens=True)
                if self._metrics:
                    with suppress(Exception):
                        self._metrics.timing("hf_infer_latency_seconds", duration)
                        self._metrics.increment("hf_infer_success")
                return self.build_result(
                    text=text, tokens=len(text.split()), latency=duration, raw=output
                )
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                if self._metrics:
                    with suppress(Exception):
                        self._metrics.increment("hf_infer_errors")
                if attempt < self._max_retries:
                    backoff = self._backoff_base * math.pow(2, attempt - 1)
                    logger.warning(
                        "HF infer failed (attempt %s/%s): %s - retrying in %.2fs",
                        attempt,
                        self._max_retries,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        "HF infer failed after %s attempts: %s", self._max_retries, exc
                    )
                    raise AdapterError(f"hf-infer-failed: {exc}") from exc

        raise AdapterError(f"hf-infer-failed: {last_exc}")

    # ------------------------------------------------------------------
    def health_check(self) -> dict:
        base = super().health_check()
        base.update(
            {
                "model_id": self._model_id,
                "agent": self._agent,
                "quantization": self._quantization_mode,
                "device": self._device,
            }
        )
        return base

    def unload(self) -> None:
        self.mark_unloaded()
        self._model = None
        self._tokenizer = None

    def metadata(self) -> dict:
        data = {
            "adapter": "hf",
            "name": self._name,
            "model_id": self._model_id,
            "agent": self._agent,
            "quantization": self._quantization_mode,
        }
        return data
