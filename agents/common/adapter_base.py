from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_TRUTHY = {"1", "true", "yes", "on"}


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


class AdapterError(RuntimeError):
    """Raised when an adapter encounters a fatal/handled error."""

    def __init__(
        self, message: str, *, code: str | None = None, extra: dict | None = None
    ) -> None:
        super().__init__(message)
        self.code = code or message.split(":", 1)[0]
        self.extra = extra or {}


@dataclass(slots=True)
class AdapterResult:
    text: str
    tokens: int | dict[str, int] | None = None
    latency: float | None = None
    raw: Any | None = None

    def as_dict(self) -> dict:
        data: dict[str, Any] = {"text": self.text}
        if self.tokens is not None:
            data["tokens"] = self.tokens
        if self.latency is not None:
            data["latency"] = self.latency
        if self.raw is not None:
            data["raw"] = self.raw
        return data


@dataclass(slots=True)
class AdapterMetadata:
    adapter: str
    name: str
    version: str | None = None
    device: str | None = None
    extra: dict[str, Any] | None = None

    def as_dict(self) -> dict:
        payload = {"adapter": self.adapter, "name": self.name}
        if self.version:
            payload["version"] = self.version
        if self.device:
            payload["device"] = self.device
        if self.extra:
            payload.update(self.extra)
        return payload


@dataclass(slots=True)
class AdapterHealth:
    loaded: bool
    name: str
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict:
        payload = {"loaded": self.loaded, "name": self.name}
        if self.details:
            payload.update(self.details)
        return payload


class BaseAdapter:
    """Adapter interface + helper utilities shared across providers."""

    def __init__(self, *, name: str = "adapter", dry_run: bool | None = None) -> None:
        self.name = name
        # Avoid clobbering subclasses that do not call super().__init__ by using getattr defaults
        if not hasattr(self, "_loaded"):
            self._loaded = False
        self._dry_run = (
            bool(dry_run)
            if dry_run is not None
            else (_env_flag("MODEL_STORE_DRY_RUN") or _env_flag("DRY_RUN"))
        )

    # ------------------------------------------------------------------
    # Lifecycle helpers
    def mark_loaded(self) -> None:
        self._loaded = True

    def mark_unloaded(self) -> None:
        self._loaded = False

    def is_loaded(self) -> bool:
        return bool(getattr(self, "_loaded", False))

    def ensure_loaded(self) -> None:
        if not self.is_loaded():
            raise AdapterError("adapter-not-loaded")

    @property
    def dry_run(self) -> bool:
        return bool(getattr(self, "_dry_run", False))

    # ------------------------------------------------------------------
    # Result helpers
    def build_result(
        self,
        *,
        text: str,
        tokens: int | dict[str, int] | None = None,
        latency: float | None = None,
        raw: Any | None = None,
    ) -> dict:
        return AdapterResult(
            text=text, tokens=tokens, latency=latency, raw=raw
        ).as_dict()

    # ------------------------------------------------------------------
    # Abstract contract -------------------------------------------------
    def load(self, model_id: str | None = None, config: dict | None = None) -> None:
        raise NotImplementedError()

    def infer(self, prompt: str, **kwargs: Any) -> dict:
        raise NotImplementedError()

    def batch_infer(self, prompts: Sequence[str], **kwargs: Any) -> list[dict]:
        return [self.infer(prompt, **kwargs) for prompt in prompts]

    def health_check(self) -> dict:
        try:
            meta = self.metadata()
        except NotImplementedError:
            meta = {}
        details = meta if isinstance(meta, dict) else {}
        return AdapterHealth(
            loaded=self.is_loaded(), name=self.name, details=details
        ).as_dict()

    def unload(self) -> None:
        raise NotImplementedError()

    def metadata(self) -> dict:
        raise NotImplementedError()
