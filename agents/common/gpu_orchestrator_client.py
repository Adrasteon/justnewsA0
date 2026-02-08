"""GPU Orchestrator Client Helper

Lightweight, conservative client wrapper for interacting with the GPU Orchestrator
service (port 8014). Provides:

* Read-only GPU telemetry retrieval with fast timeout & safe fallback
* Policy retrieval with TTL-based caching (default 30s)
* SAFE_MODE awareness helper
* Zero-exception interface (all failures return structured fallbacks)

Design Principles (Phase 1):
* NEVER block agent critical path > a few milliseconds on failure paths
* ALWAYS fail closed (assume SAFE_MODE / CPU fallback if orchestrator unreachable)
* DO NOT introduce background threads or async complexity at this stage
* KEEP dependencies minimal (requests only)

Future Extensions (Phase 2+):
* Optional async support via httpx
* Allocation/lease helpers when orchestrator exposes those endpoints
* Structured metrics integration (success/error counters, latency histograms)
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import requests

from common.observability import get_logger

logger = get_logger(__name__)

DEFAULT_BASE_URL = os.environ.get("GPU_ORCHESTRATOR_URL", "http://localhost:8014")
REQUEST_TIMEOUT: tuple[float, float] = (1.5, 3.0)  # (connect, read) seconds
DEFAULT_POLICY_TTL = float(os.environ.get("GPU_ORCHESTRATOR_POLICY_TTL", "30"))


_FALLBACK_POLICY: dict[str, Any] = {
    "max_memory_per_agent_mb": 2048,
    "allow_fractional_shares": True,
    "kill_on_oom": False,
    "safe_mode_read_only": True,  # Assume SAFE_MODE if we cannot verify
    "_fallback": True,
}


class GPUOrchestratorClient:
    """Synchronous client for the GPU Orchestrator service.

    This client NEVER raises network exceptions outward. All errors are converted
    into structured fallback responses so downstream agent logic can remain
    simple and robust.
    """

    def __init__(
        self,
        base_url: str | None = None,
        policy_ttl: float = DEFAULT_POLICY_TTL,
        request_timeout: tuple[float, float] = REQUEST_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.policy_ttl = policy_ttl
        self.request_timeout = request_timeout
        self._policy_cache: dict[str, Any] | None = None
        self._policy_cache_time: float = 0.0
        self._lock = threading.Lock()
        # Failure logging backoff (avoid log spam)
        self._last_failure_log: float = 0.0
        self._failure_log_interval: float = 60.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_gpu_info(self) -> dict[str, Any]:
        """Return GPU telemetry.

        Success: {'available': True, 'gpus': [...], ...}
        Failure: {'available': False, 'gpus': [], 'message': str}
        """
        url = f"{self.base_url}/gpu/info"
        try:
            resp = requests.get(url, timeout=self.request_timeout)
            if resp.status_code == 200:
                data = resp.json()
                # Ensure minimal shape
                if "available" not in data:
                    data["available"] = False
                if "gpus" not in data:
                    data["gpus"] = []
                return data
            return {
                "available": False,
                "gpus": [],
                "message": f"unexpected_status:{resp.status_code}",
            }
        except Exception as e:  # noqa: BLE001 - broad to guarantee fail-safe
            self._maybe_log_failure(f"GPU info fetch failed: {e}")
            return {"available": False, "gpus": [], "message": "unreachable"}

    def get_policy(self, force_refresh: bool = False) -> dict[str, Any]:
        """Return orchestrator policy with TTL caching.

        Args:
            force_refresh: Ignore cache and fetch from service.
        """
        with self._lock:
            if (
                not force_refresh
                and self._policy_cache
                and (time.time() - self._policy_cache_time) < self.policy_ttl
            ):
                return self._policy_cache

        url = f"{self.base_url}/policy"
        try:
            resp = requests.get(url, timeout=self.request_timeout)
            if resp.status_code == 200:
                policy = resp.json()
                # Defensive: enforce expected keys
                policy.setdefault("safe_mode_read_only", True)
                with self._lock:
                    self._policy_cache = policy
                    self._policy_cache_time = time.time()
                return policy
            self._maybe_log_failure(
                f"Policy fetch unexpected status {resp.status_code}"
            )
            return _FALLBACK_POLICY
        except Exception as e:  # noqa: BLE001
            self._maybe_log_failure(f"Policy fetch failed: {e}")
            return _FALLBACK_POLICY

    def safe_mode_active(self) -> bool:
        """Whether SAFE_MODE is active (assume active on uncertainty)."""
        policy = self.get_policy()
        return bool(policy.get("safe_mode_read_only", True))

    def cpu_fallback_decision(self) -> dict[str, Any]:
        """Return a structured CPU fallback decision envelope.

        This can be expanded later with heuristics / policy (e.g., triggered when
        GPU unavailable but workload optional).
        """
        gpu_info = self.get_gpu_info()
        safe_mode = self.safe_mode_active()
        return {
            "use_gpu": (gpu_info.get("available") and not safe_mode),
            "safe_mode": safe_mode,
            "gpu_available": gpu_info.get("available", False),
            "policy_fallback": gpu_info.get("available") is False,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _maybe_log_failure(self, message: str) -> None:
        now = time.time()
        if now - self._last_failure_log > self._failure_log_interval:
            logger.warning(message)
            self._last_failure_log = now


__all__ = [
    "GPUOrchestratorClient",
]
