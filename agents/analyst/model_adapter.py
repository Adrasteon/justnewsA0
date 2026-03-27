"""High-accuracy sentiment/bias scoring backed by the Analyst Qwen model."""

from __future__ import annotations

import json
import os
import textwrap
import time
from dataclasses import dataclass
from typing import Any

from agents.common.openai_adapter import OpenAIAdapter
from common.observability import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a rigorous news analysis classifier. Evaluate the provided text"
    " for overall sentiment and bias. Respond with strict JSON using the schema:\n"
    "{\n"
    '  "sentiment_label": "positive|neutral|negative",\n'
    '  "sentiment_confidence": 0.0-1.0,\n'
    '  "sentiment_intensity": "mild|moderate|strong",\n'
    '  "sentiment_positive": 0.0-1.0,\n'
    '  "sentiment_negative": 0.0-1.0,\n'
    '  "bias_level": "minimal|low|medium|high",\n'
    '  "bias_score": 0.0-1.0,\n'
    '  "bias_confidence": 0.0-1.0,\n'
    '  "rationale": "One concise sentence explaining the judgment"\n'
    "}\n"
    "Keep the response compact and valid JSON only."
)


@dataclass(frozen=True)
class AdapterResult:
    sentiment: dict[str, Any]
    bias: dict[str, Any]
    raw: dict[str, Any]


class AnalystModelAdapter:
    """Qwen-backed helper that emits structured sentiment/bias scores."""

    def __init__(self) -> None:
        self.enabled = os.environ.get("ANALYST_DISABLE_MISTRAL", "0").lower() not in {"1", "true"}

        self.adapter = OpenAIAdapter(
            name="analyst_qwen",
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            system_prompt=SYSTEM_PROMPT,
            temperature=0.15,
            max_tokens=360,
            timeout=40.0
        )

    def classify(self, text: str) -> AdapterResult | None:
        if not self.enabled:
            return None

        snippet = textwrap.shorten(text or "", width=6000, placeholder="...")
        if not snippet:
            return None

        user_block = f"Text to evaluate:\n'''{snippet}'''\n\nReturn valid JSON."
        start = time.perf_counter()

        try:
            # Ensure the adapter is loaded before first use
            if hasattr(self.adapter, "load"):
                self.adapter.load()
            self.adapter.ensure_loaded()
            result = self.adapter.infer(user_block)
            doc = self._parse_response(result.get("text", ""))
        except Exception as e:
            logger.warning(f"Analyst Qwen generation failed: {e}")
            doc = None

        elapsed = time.perf_counter() - start
        if not doc:
            return None
        return self._normalize(doc, elapsed)

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        try:
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception:
            return None

    # Internal helpers -------------------------------------------------

    def _normalize(
        self, payload: dict[str, Any], elapsed: float
    ) -> AdapterResult | None:
        try:
            sentiment_label = str(payload.get("sentiment_label", "neutral")).lower()
            if sentiment_label not in {"positive", "negative", "neutral"}:
                sentiment_label = "neutral"
            sentiment_conf = float(payload.get("sentiment_confidence", 0.72))
            intensity = payload.get(
                "sentiment_intensity"
            ) or self._confidence_to_intensity(sentiment_conf)
            positive_score = float(
                payload.get(
                    "sentiment_positive",
                    sentiment_conf
                    if sentiment_label == "positive"
                    else 1 - sentiment_conf
                    if sentiment_label == "negative"
                    else 0.33,
                )
            )
            negative_score = float(
                payload.get("sentiment_negative", 1.0 - positive_score)
            )

            bias_score = float(payload.get("bias_score", 0.35))
            bias_level = payload.get("bias_level") or self._bias_level_from_score(
                bias_score
            )
            bias_conf = float(
                payload.get("bias_confidence", min(bias_score + 0.25, 0.95))
            )

            sentiment = {
                "dominant_sentiment": sentiment_label,
                "confidence": sentiment_conf,
                "subjectivity": "subjective"
                if sentiment_conf > 0.6
                else "objective",  # Approximated
                "intensity": intensity,
                "positive": positive_score,
                "negative": negative_score,
                "neutral": max(
                    0.0, 1.0 - (positive_score + negative_score)
                ),  # Ensure sum <= 1
                "method": "qwen_adapter",
                "model_name": "Qwen/Qwen2.5-14B-Instruct-AWQ",
                "analysis_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "reasoning": payload.get("rationale", "Adapter judgment"),
                "processing_time": elapsed,
            }

            bias = {
                "has_bias": bias_score >= 0.35,
                "bias_score": max(0.0, min(bias_score, 1.0)),
                "bias_level": bias_level,
                "confidence": max(0.0, min(bias_conf, 0.99)),
                "political_bias": float(
                    payload.get("political_bias", bias_score * 0.6)
                ),
                "emotional_bias": float(
                    payload.get("emotional_bias", bias_score * 0.8)
                ),
                "factual_bias": float(
                    payload.get("factual_bias", max(0.0, 1.0 - bias_score))
                ),
                "reasoning": payload.get("rationale", "Adapter judgment"),
                "method": "qwen_adapter",
                "model_used": "Qwen/Qwen2.5-14B-Instruct-AWQ",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "processing_time": elapsed,
            }
            return AdapterResult(sentiment=sentiment, bias=bias, raw=payload)
        except Exception as exc:
            logger.warning("Failed to normalize Analyst adapter output: %s", exc)
            return None

    @staticmethod
    def _confidence_to_intensity(confidence: float) -> str:
        if confidence >= 0.8:
            return "strong"
        if confidence >= 0.6:
            return "moderate"
        return "mild"

    @staticmethod
    def _bias_level_from_score(score: float) -> str:
        if score >= 0.7:
            return "high"
        if score >= 0.45:
            return "medium"
        if score >= 0.25:
            return "low"
        return "minimal"

# Alias for compat
AnalystMistralAdapter = AnalystModelAdapter
