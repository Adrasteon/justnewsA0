"""High-accuracy editorial critique helper backed by the Critic Qwen adapter."""

from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass
from typing import Any

from agents.common.openai_adapter import OpenAIAdapter
from common.observability import get_logger

logger = get_logger(__name__)

MODEL_ADAPTER_NAME = "critic_qwen_v1"
DISABLE_ENV = "CRITIC_DISABLE_MISTRAL"
SYSTEM_PROMPT = (
    "You are the JustNews editorial chief. Review the provided article and respond\n"
    "with JSON using this schema:{\n"
    '  "quality_score": 0.0-1.0,\n'
    '  "bias_score": 0.0-1.0,\n'
    '  "consistency_score": 0.0-1.0,\n'
    '  "readability_score": 0.0-1.0,\n'
    '  "originality_score": 0.0-1.0,\n'
    '  "overall_score": 0.0-1.0,\n'
    '  "assessment": "One brief paragraph",\n'
    '  "recommendations": ["sentence", ...]\n'
    "}\n"
    "Focus on accuracy; when unsure lower the corresponding score. Output valid JSON only."
)


@dataclass(frozen=True)
class CriticAssessment:
    quality: float
    bias: float
    consistency: float
    readability: float
    originality: float
    overall: float
    assessment: str
    recommendations: list[str]


class CriticModelAdapter:
    """Inference helper for editorial critiques using Qwen."""

    def __init__(self) -> None:
        self.enabled = os.environ.get(DISABLE_ENV, "0").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.max_chars = int(os.environ.get("CRITIC_MAX_CHARS", "6000"))
        
        self.adapter = OpenAIAdapter(
            name="critic_qwen",
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            system_prompt=SYSTEM_PROMPT,
            temperature=float(os.environ.get("CRITIC_TEMPERATURE", "0.2")),
            max_tokens=400,
            timeout=50.0
        )
        
        self._last_hash: int | None = None
        self._last_result: CriticAssessment | None = None

    def review(self, content: str, url: str | None = None) -> CriticAssessment | None:
        if not self.enabled or not content.strip():
            return None

        content_hash = hash((content, url))
        if self._last_hash == content_hash and self._last_result is not None:
            return self._last_result

        trimmed = textwrap.shorten(
            content.strip(), width=self.max_chars, placeholder="..."
        )
        url_line = f"\nSource: {url}" if url else ""
        user_block = f"Article:\n'''{trimmed}'''{url_line}\n\nReturn valid JSON."

        try:
            self.adapter.ensure_loaded()
            result = self.adapter.infer(user_block)
            payload = self._parse_completion(result.get("text", ""))
            
            assessment = self._normalize(payload)
            if assessment:
                self._last_hash = content_hash
                self._last_result = assessment
            return assessment
        except Exception as e:
            logger.warning(f"Critic Qwen generation failed: {e}")
            return None

    def _parse_completion(self, completion: str) -> dict[str, Any] | None:
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
                logger.debug("Failed to parse Critic adapter JSON: %s", snippet)
                return None

    def _normalize(self, payload: dict[str, Any] | None) -> CriticAssessment | None:
        if not payload:
            return None
        try:
            def clamp(value: Any) -> float:
                try:
                    v = float(value)
                    return max(0.0, min(v, 1.0))
                except (ValueError, TypeError):
                    return 0.5

            quality = clamp(payload.get("quality_score", 0.6))
            bias = clamp(payload.get("bias_score", 0.4))
            consistency = clamp(payload.get("consistency_score", 0.5))
            readability = clamp(payload.get("readability_score", 0.7))
            originality = clamp(payload.get("originality_score", 0.6))
            overall = clamp(
                payload.get("overall_score", (quality + consistency + readability) / 3)
            )
            assessment = str(
                payload.get("assessment", "Adapter could not summarize its critique.")
            )
            recommendations = payload.get("recommendations")
            if not isinstance(recommendations, list):
                recommendations = [str(recommendations)] if recommendations else []
            recommendations = [
                str(item) for item in recommendations if str(item).strip()
            ]
            return CriticAssessment(
                quality=quality,
                bias=bias,
                consistency=consistency,
                readability=readability,
                originality=originality,
                overall=overall,
                assessment=assessment,
                recommendations=recommendations,
            )
        except Exception as exc:
            logger.warning("Failed to normalize Critic adapter output: %s", exc)
            return None

# Alias for compat
CriticMistralAdapter = CriticModelAdapter
