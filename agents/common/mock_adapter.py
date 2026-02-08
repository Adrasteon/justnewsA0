from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .adapter_base import AdapterError, BaseAdapter


class MockAdapter(BaseAdapter):
    """Deterministic adapter implementation used for tests and CI runs."""

    def __init__(
        self,
        *,
        name: str = "mock",
        default_text: str = "[MOCK:{name}] {prompt}",
        responses: Mapping[str, str] | None = None,
        failure_prompts: Iterable[str] | None = None,
        latency_seconds: float = 0.0,
        token_counter: Callable[[str], int] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name=name, dry_run=True)
        self._default_text_template = default_text
        self._responses = dict(responses or {})
        self._failure_prompts = set(failure_prompts or [])
        self._latency_seconds = max(0.0, float(latency_seconds))
        self._token_counter = token_counter or (
            lambda prompt: max(1, len(prompt.split()))
        )
        self._metadata = metadata or {"adapter": "mock", "name": name}
        self._model_id: str | None = None
        self._invocation_count = 0

    # ------------------------------------------------------------------
    def load(self, model_id: str | None = None, config: dict | None = None) -> None:
        if config:
            self._responses.update(config.get("responses", {}))
            if "default_text" in config:
                self._default_text_template = str(config["default_text"])
            if "failure_prompts" in config:
                self._failure_prompts.update(config["failure_prompts"])
            if "latency_seconds" in config:
                self._latency_seconds = max(0.0, float(config["latency_seconds"]))
        self._model_id = model_id or "mock-model"
        self._invocation_count = 0
        self.mark_loaded()

    def infer(self, prompt: str, **kwargs: Any) -> dict:
        self.ensure_loaded()
        if prompt in self._failure_prompts:
            raise AdapterError("mock-forced-failure", extra={"prompt": prompt})

        text_template = self._responses.get(prompt, self._default_text_template)
        self._invocation_count += 1
        start = time.time()
        if self._latency_seconds:
            time.sleep(self._latency_seconds)
        text = text_template.format(
            prompt=prompt, name=self.name, count=self._invocation_count
        )
        latency = time.time() - start
        tokens = self._token_counter(prompt)
        raw = {
            "prompt": prompt,
            "mock": True,
            "model_id": self._model_id,
            "invocation": self._invocation_count,
        }
        return self.build_result(text=text, tokens=tokens, latency=latency, raw=raw)

    def health_check(self) -> dict:
        data = {
            "loaded": self.is_loaded(),
            "name": self.name,
            "invocations": self._invocation_count,
            "responses": len(self._responses),
        }
        data.update({k: v for k, v in self._metadata.items() if k not in data})
        return data

    def unload(self) -> None:
        self.mark_unloaded()
        self._model_id = None
        self._invocation_count = 0

    def metadata(self) -> dict:
        payload = dict(self._metadata)
        if self._model_id:
            payload.setdefault("model_id", self._model_id)
        return payload
