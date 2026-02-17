"""Shared helpers for adapters that prompt Mistral-7B and expect JSON output."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from common.observability import get_logger

try:  # pragma: no cover - optional heavy dependency
    import torch

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

logger = get_logger(__name__)


class BaseMistralJSONAdapter:
    """Minimal runner that loads a Mistral adapter and returns JSON completions."""

    def __init__(
        self,
        *,
        agent_name: str,
        adapter_name: str,
        system_prompt: str,
        disable_env: str,
        defaults: dict[str, Any] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.adapter_name = adapter_name
        self.system_prompt = system_prompt.strip()
        self.disable_env = disable_env
        cfg = defaults or {}
        prefix = agent_name.upper()
        self.max_chars = int(
            os.environ.get(f"{prefix}_MISTRAL_MAX_CHARS", cfg.get("max_chars", 6000))
        )
        self.max_input_tokens = int(
            os.environ.get(
                f"{prefix}_MISTRAL_MAX_INPUT_TOKENS", cfg.get("max_input_tokens", 2048)
            )
        )
        self.max_new_tokens = int(
            os.environ.get(
                f"{prefix}_MISTRAL_MAX_NEW_TOKENS", cfg.get("max_new_tokens", 320)
            )
        )
        self.temperature = float(
            os.environ.get(f"{prefix}_MISTRAL_TEMPERATURE", cfg.get("temperature", 0.2))
        )
        self.top_p = float(
            os.environ.get(f"{prefix}_MISTRAL_TOP_P", cfg.get("top_p", 0.9))
        )
        self.enabled = os.environ.get(disable_env, "0").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.model = None
        self.tokenizer = None
        self._load_attempted = False
        self._load_error: str | None = None

    # Loading -----------------------------------------------------------------
    def _ensure_loaded(self) -> bool:
        if not self.enabled:
            return False
        if self.model is not None and self.tokenizer is not None:
            return True
        if self._load_attempted:
            return False
        self._load_attempted = True

        if not TORCH_AVAILABLE:
            self._load_error = "torch-missing"
            logger.debug("PyTorch unavailable; cannot load %s adapter", self.agent_name)
            return False
        try:
            from agents.common.mistral_loader import load_mistral_adapter_or_base
        except Exception as exc:  # pragma: no cover
            self._load_error = str(exc)
            logger.warning(
                "Shared loader import failed for agent=%s: %s", self.agent_name, exc
            )
            return False

        model, tokenizer = load_mistral_adapter_or_base(
            self.agent_name,
            adapter_name=self.adapter_name,
            model_kwargs={
                "device_map": "auto",
                "low_cpu_mem_usage": True,
                "trust_remote_code": True,
            },
            tokenizer_kwargs={"use_fast": True},
        )
        if model is None or tokenizer is None:
            self._load_error = "adapter-or-base-load-failed"
            logger.warning(
                "Adapter load returned empty handles for agent=%s", self.agent_name
            )
            return False
        try:
            model.eval()
        except Exception:
            pass
        self.model = model
        self.tokenizer = tokenizer
        logger.info(
            "Loaded %s Mistral weights (adapter=%s)", self.agent_name, self.adapter_name
        )
        return True

    # Core inference helpers ---------------------------------------------------
    def _truncate_content(self, content: str) -> str:
        text = (content or "").strip()
        if not text:
            return ""
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars].rsplit(" ", 1)[0]

    def _format_prompt(self, messages: list[dict[str, str]]) -> str:
        if self.tokenizer and hasattr(self.tokenizer, "apply_chat_template"):
            try:
                return self.tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
            except Exception:
                pass
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"<s>[SYS]{content}[/SYS]\n")
            elif role == "user":
                parts.append(f"[INST] {content} [/INST]\n")
            else:
                parts.append(content)
        return "\n".join(parts)

    def _chat(self, messages: list[dict[str, str]]) -> str | None:
        if not self._ensure_loaded() or not TORCH_AVAILABLE:
            return None
        prompt = self._format_prompt(messages)
        try:
            inputs = self.tokenizer(
                prompt,
                return_tensors="pt",
                truncation=True,
                max_length=self.max_input_tokens,
            )
        except Exception as exc:
            logger.warning("Tokenizer failed for agent=%s: %s", self.agent_name, exc)
            return None

        device = None
        if hasattr(self.model, "device"):
            device = self.model.device
        if device is not None:
            try:
                inputs = {k: v.to(device) for k, v in inputs.items()}
            except Exception:
                pass

        gen_kwargs = {
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "do_sample": self.temperature > 0,
            "eos_token_id": getattr(self.tokenizer, "eos_token_id", None),
        }
        try:
            with torch.no_grad():  # type: ignore[attr-defined]
                output_ids = self.model.generate(**inputs, **gen_kwargs)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("Generation failed for agent=%s: %s", self.agent_name, exc)
            return None

        try:
            generated = output_ids[:, inputs["input_ids"].shape[-1] :]
        except Exception:
            generated = output_ids
        try:
            completion = self.tokenizer.decode(
                generated[0], skip_special_tokens=True
            ).strip()
        except Exception:
            completion = ""
        return completion or None

    def _parse_json(self, completion: str) -> dict[str, Any] | None:
        if not completion:
            return None
        snippet = completion.strip()
        fenced = re.search(r"```(?:json)?(.*?)```", snippet, flags=re.DOTALL)
        if fenced:
            snippet = fenced.group(1)
        brace = re.search(r"\{.*\}", snippet, flags=re.DOTALL)
        if brace:
            snippet = brace.group(0)
        snippet = snippet.strip()
        if not snippet:
            return None
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            try:
                sanitized = snippet.replace("'", '"')
                sanitized = re.sub(r",\s*\}", "}", sanitized)
                return json.loads(sanitized)
            except Exception:
                logger.debug(
                    "JSON parse failed for agent=%s payload=%s",
                    self.agent_name,
                    snippet[:200],
                )
                return None

    def _chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any] | None:
        completion = self._chat(messages)
        if not completion:
            return None
        return self._parse_json(completion)

    # Public helpers -----------------------------------------------------------
    @property
    def is_available(self) -> bool:
        return (
            self.enabled
            and self.model is not None
            and self.tokenizer is not None
            and TORCH_AVAILABLE
        )
