from __future__ import annotations

import logging
import math
import os
import time
from contextlib import suppress
from typing import Any

from common.metrics import get_metrics

from .adapter_base import AdapterError, BaseAdapter

logger = logging.getLogger(__name__)


class OpenAIAdapter(BaseAdapter):
    """OpenAI adapter with dry-run support, retries, and streaming hooks."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        name: str = "openai",
        model: str = "gpt-3.5-turbo",
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        user: str | None = None,
        timeout: float = 15.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        extra_headers: dict | None = None,
    ) -> None:
        super().__init__(name=name)
        self._model = model
        self._system_prompt = system_prompt
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._user = user
        self._timeout = float(timeout)
        self._max_retries = int(max_retries)
        self._backoff_base = float(backoff_base)
        self._extra_headers = extra_headers or {}
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._base_url = base_url or os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")
        try:
            self._metrics = get_metrics(self.name)
        except Exception:
            self._metrics = None
        self._client = None

    # ------------------------------------------------------------------
    def _build_messages(self, prompt: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    # Compatibility helpers expected by legacy shim adapters -----------------
    def _truncate_content(self, text: str, limit: int = 4000) -> str:
        if text is None:
            return ""
        return text[:limit]

    def _ensure_loaded(self) -> bool:
        if self.is_loaded():
            return True
        try:
            self.load(None)
        except Exception:
            return False
        return self.is_loaded()

    def _chat_json(self, messages: list[dict[str, str]]) -> dict | None:
        if not messages:
            return None
        prompt_parts = [m.get("content", "") for m in messages if isinstance(m, dict)]
        prompt = "\n\n".join(part for part in prompt_parts if part)
        result = self.infer(prompt)
        text = (result or {}).get("text", "") if isinstance(result, dict) else ""
        if not text:
            return None
        import json

        cleaned = text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            return {"text": text}

    def _client_kwargs(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "model": self._model,
            "temperature": self._temperature,
            "timeout": self._timeout,
        }
        if self._max_tokens:
            data["max_tokens"] = self._max_tokens
        if self._user:
            data["user"] = self._user
        if self._extra_headers:
             data["extra_headers"] = self._extra_headers
        return data

    # ------------------------------------------------------------------
    def load(self, model_id: str | None = None, config: dict | None = None) -> None:
        if config:
            self._model = config.get("model", self._model)
        if self.dry_run:
            self.mark_loaded()
            return

        if not self._api_key:
            # For vLLM, API key might be optional, but OpenAI client usually requires it.
            # We'll allow a dummy key if base_url is set, to support vLLM usage easily.
            if self._base_url:
                self._api_key = "***"
            else:
                raise AdapterError("openai-missing-api-key")

        try:
            import openai as openai_module

            client_args = {"api_key": self._api_key}
            if self._base_url:
                client_args["base_url"] = self._base_url
            if self._extra_headers:
                client_args["default_headers"] = self._extra_headers

            # New SDK path
            OpenAI_cls = getattr(openai_module, "OpenAI", None)
            if OpenAI_cls is not None:
                self._client = OpenAI_cls(**client_args)
            else:
                # Legacy/testing shim path: rely on module-level ChatCompletion API
                self._client = openai_module

            self.mark_loaded()
        except Exception as exc:  # pragma: no cover
            raise AdapterError(f"openai-load-failed: {exc}") from exc

    # ------------------------------------------------------------------
    def ensure_loaded(self) -> None:
        """Compatibility: lazy-load on first use for legacy adapter callers."""
        if self.is_loaded():
            return
        try:
            self.load(None)
        except Exception as exc:
            raise AdapterError(f"openai-adapter-load-failed: {exc}") from exc
        if not self.is_loaded():
            raise AdapterError("openai-adapter-not-loaded")

    def infer(self, prompt: str, **overrides: Any) -> dict:
        self.ensure_loaded()

        if self.dry_run:
            start = time.time()
            duration = time.time() - start
            if self._metrics:
                with suppress(Exception):
                    self._metrics.timing("openai_infer_latency_seconds", duration)
                    self._metrics.increment("openai_infer_success")
            return self.build_result(
                text=f"[DRYRUN-openai:{self._model}] Simulated response to: {prompt[:120]}",
                raw={"simulated": True},
                tokens=len(prompt.split()),
                latency=duration,
            )

        if self._client is None:
            raise AdapterError("openai-client-uninitialized")

        payload = self._client_kwargs()
        # Clean up legacy timeouts
        if "request_timeout" in payload:
             del payload["request_timeout"]
        payload["timeout"] = self._timeout

        payload.update({k: v for k, v in overrides.items() if v is not None})
        messages = self._build_messages(prompt)
        payload["messages"] = messages

        # Handle extra_headers manually if invalid for create()
        # In v1, extra_headers are usually passed to the client, or via explicit extra_headers param in some calls?
        # create() allows extra_headers/extra_query
        if "extra_headers" in payload:
             extra_headers = payload.pop("extra_headers")
             payload["extra_headers"] = extra_headers

        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            start = time.time()
            try:
                if hasattr(self._client, "chat") and hasattr(self._client.chat, "completions"):
                    resp = self._client.chat.completions.create(**payload)
                else:
                    # Compatibility path for module-level legacy/testing shims.
                    resp = self._client.ChatCompletion.create(**payload)
                duration = time.time() - start

                # Extract content
                text = ""
                if resp.choices:
                    text = resp.choices[0].message.content or ""

                if self._metrics:
                    with suppress(Exception):
                        self._metrics.timing("openai_infer_latency_seconds", duration)
                        self._metrics.increment("openai_infer_success")
                return self.build_result(
                    text=text, tokens=len(text.split()), latency=duration, raw=resp
                )
            except Exception as exc:  # pragma: no cover
                last_exc = exc
                if self._metrics:
                    with suppress(Exception):
                        self._metrics.increment("openai_infer_errors")
                if attempt < self._max_retries:
                    backoff = self._backoff_base * math.pow(2, attempt - 1)
                    logger.warning(
                        "OpenAI infer failed (attempt %s/%s): %s - retrying in %.2fs",
                        attempt,
                        self._max_retries,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        "OpenAI infer failed after %s attempts: %s",
                        self._max_retries,
                        exc,
                    )
                    raise AdapterError(f"openai-infer-failed: {exc}") from exc
        raise AdapterError(f"openai-infer-failed: {last_exc}")

    # ------------------------------------------------------------------
    def health_check(self) -> dict:
        base = super().health_check()
        base.update({"model": self._model, "user": self._user})
        return base

    def unload(self) -> None:
        self._client = None
        self.mark_unloaded()

    @property
    def model(self):
        return self._model

    @model.setter
    def model(self, value):
        self._model = value

    @property
    def tokenizer(self):
        # Maintained for compatibility with adapters that clear tokenizer on unload.
        return getattr(self, "_tokenizer", None)

    @tokenizer.setter
    def tokenizer(self, value):
        self._tokenizer = value

    def metadata(self) -> dict:
        return {
            "adapter": "openai",
            "name": self.name,
            "model": self._model,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
