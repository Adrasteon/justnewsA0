"""Paywall detection helper for the crawler."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

import requests

from common.observability import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PaywallDetectionResult:
    """Structured paywall detection outcome."""

    is_paywall: bool
    confidence: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def should_skip(self) -> bool:
        """Return ``True`` when the crawler should abandon the article."""
        return self.is_paywall and self.confidence >= 0.6


class PaywallDetector:
    """Heuristic + optional AI-assisted paywall detection."""

    HEURISTIC_KEYWORDS = (
        "subscribe to read",
        "subscription required",
        "log in to continue",
        "sign in to continue",
        "become a subscriber",
        "this is premium content",
        "register for free and continue",
        "already a subscriber",
        "purchase this article",
        "membership required",
    )

    def __init__(
        self,
        *,
        enable_remote_analysis: bool = False,
        mcp_bus_url: str = "http://localhost:8000",
        max_remote_chars: int = 6000,
        request_timeout: tuple[float, float] = (2.0, 10.0),
    ) -> None:
        self.enable_remote_analysis = enable_remote_analysis
        self.mcp_bus_url = mcp_bus_url.rstrip("/")
        self.max_remote_chars = max_remote_chars
        self.request_timeout = request_timeout
        self._session = requests.Session()

    async def analyze(
        self,
        *,
        url: str,
        html: str,
        text: str | None = None,
    ) -> PaywallDetectionResult:
        """Analyse an article candidate for paywall characteristics."""
        reasons: list[str] = []
        confidence = 0.0

        lowered = html.lower()
        for keyword in self.HEURISTIC_KEYWORDS:
            if keyword in lowered:
                reasons.append(f"matched keyword: {keyword}")
                confidence = max(confidence, 0.6)

        # Simple detection for short content with paywall hints
        if text and len(text.strip()) < 400:
            reasons.append("extracted text too short")
            confidence = max(confidence, 0.4)

        remote_reason: str | None = None
        if self.enable_remote_analysis:
            try:
                remote = await self._remote_check(url=url, text=text or html)
                if remote:
                    confidence = max(confidence, remote.confidence)
                    reasons.extend(remote.reasons)
                    remote_reason = remote.metadata.get("source")
            except Exception as exc:  # noqa: BLE001 - resilience preferred
                logger.debug("Remote paywall analysis failed for %s: %s", url, exc)

        result = PaywallDetectionResult(
            is_paywall=confidence >= 0.6,
            confidence=confidence,
            reasons=reasons,
            metadata={"remote_source": remote_reason or "heuristic"},
        )
        logger.debug(
            "Paywall analysis for %s => is_paywall=%s confidence=%.2f reasons=%s",
            url,
            result.is_paywall,
            result.confidence,
            result.reasons,
        )
        return result

    async def _remote_check(
        self, *, url: str, text: str
    ) -> PaywallDetectionResult | None:
        """Offload analysis to the Analyst agent via MCP bus."""
        truncated = text[: self.max_remote_chars]

        payload = {
            "agent": "analyst",
            "tool": "detect_bias",
            "args": [truncated],
            "kwargs": {"metadata": {"url": url, "analysis": "paywall"}},
        }
        response = await asyncio.to_thread(
            self._session.post,
            f"{self.mcp_bus_url}/call",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        result_payload = data.get("data") or {}
        signals = result_payload.get("bias_indicators", [])

        reasons: list[str] = []
        confidence = 0.0
        for indicator in signals:
            label = indicator.get("label", "")
            score = float(indicator.get("score", 0.0))
            if "paywall" in label.lower() or "subscription" in label.lower():
                reasons.append(f"remote indicator: {label} ({score:.2f})")
                confidence = max(confidence, min(0.9, score))

        if not reasons:
            return None

        return PaywallDetectionResult(
            is_paywall=confidence >= 0.6,
            confidence=confidence,
            reasons=reasons,
            metadata={"source": "analyst"},
        )
