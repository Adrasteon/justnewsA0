"""High-accuracy claim verification helper backed by the Fact Checker Qwen adapter."""

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



# Configured for Qwen 2.5 14B
MODEL_ADAPTER_NAME = "Qwen/Qwen2.5-14B-Instruct-AWQ"
DISABLE_ENV = "FACT_CHECKER_DISABLE_QWEN"
SYSTEM_PROMPT = (
    "You are an expert investigative fact checker. Given a claim and optional context,\n"
    "respond with strict JSON describing whether the claim is verified, refuted, or unclear.\n"
    "Schema:{\n"
    '  "verdict": "verified|refuted|unclear",\n'
    '  "confidence": 0.0-1.0,\n'
    '  "score": 0.0-1.0,\n'
    '  "rationale": "Single concise sentence",\n'
    '  "evidence_needed": "yes|no"\n'
    "}\n"
    "Always emit valid JSON with double quotes only."
)


@dataclass(frozen=True)
class ClaimAssessment:
    verdict: str
    confidence: float
    score: float
    rationale: str
    evidence_needed: bool


class FactCheckerQwenAdapter:
    """Qwen-backed inference helper for fact-check verification."""

    def __init__(self) -> None:
        self.enabled = os.environ.get(DISABLE_ENV, "0").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._dry_run = (
            os.environ.get("MODEL_STORE_DRY_RUN") == "1"
            or os.environ.get("DRY_RUN") == "1"
        )
        self.max_tokens = int(
            os.environ.get("FACT_CHECKER_QWEN_MAX_TOKENS", "1024")
        )
        self.temperature = float(
            os.environ.get("FACT_CHECKER_QWEN_TEMPERATURE", "0.0")
        )
        
        # Initialize OpenAI/vLLM Adapter targeting Qwen
        self.adapter = OpenAIAdapter(
            name="fact_checker_qwen",
            model=os.environ.get("VLLM_MODEL", MODEL_ADAPTER_NAME),
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            system_prompt=SYSTEM_PROMPT,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=30.0
        )

    def evaluate_claim(
        self, claim: str, context: str | None = None
    ) -> ClaimAssessment | None:
        if not self.enabled or not claim.strip():
            return None

        if self._dry_run:
            return self._simulate_assessment(claim, context)

        try:
            self.adapter.ensure_loaded()
            
            # Simple prompt construction
            prompt = f"Claim: {claim}\n"
            if context:
                prompt += f"Context: {textwrap.shorten(context, width=4000)}\n"
            
            # Request JSON output
            result = self.adapter.infer(prompt)
            payload = self._parse_completion(result.get("text", ""))
            return self._normalize(payload) if payload else None
        except Exception as e:
            logger.warning(f"Qwen evaluation failed: {e}")
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
                logger.debug("Failed to parse fact-checker adapter JSON: %s", snippet)
                return None

    def _normalize(self, payload: dict[str, Any]) -> ClaimAssessment | None:
        try:
            verdict = str(payload.get("verdict", "unclear")).lower()
            if verdict not in {"verified", "refuted", "unclear"}:
                verdict = "unclear"
            confidence = float(payload.get("confidence", 0.65))
            score = float(
                payload.get(
                    "score",
                    0.6
                    if verdict == "verified"
                    else 0.3
                    if verdict == "refuted"
                    else 0.5,
                )
            )
            rationale = str(
                payload.get("rationale", "Model could not justify the verdict.")
            )
            evidence_needed = str(payload.get("evidence_needed", "no")).lower() in {
                "yes",
                "true",
            }
            return ClaimAssessment(
                verdict=verdict,
                confidence=max(0.0, min(confidence, 1.0)),
                score=max(0.0, min(score, 1.0)),
                rationale=rationale,
                evidence_needed=evidence_needed,
            )
        except Exception as exc:
            logger.warning("Failed to normalize fact-checker adapter output: %s", exc)
            return None

    def _simulate_assessment(self, claim: str, context: str | None) -> ClaimAssessment:
        """Generate a deterministic dry-run ClaimAssessment."""

        fingerprint = abs(hash((claim, context))) % 100
        bucket = fingerprint % 3
        if bucket == 0:
            verdict = "verified"
            score = 0.82
        elif bucket == 1:
            verdict = "refuted"
            score = 0.35
        else:
            verdict = "unclear"
            score = 0.55

        confidence = min(0.99, 0.65 + (fingerprint % 7) * 0.035)
        rationale = (
            "Dry-run verdict generated deterministically — run without MODEL_STORE_DRY_RUN=1 "
            "to obtain live fact-checking output."
        )
        evidence_needed = verdict != "verified"
        return ClaimAssessment(
            verdict=verdict,
            confidence=confidence,
            score=score,
            rationale=rationale,
            evidence_needed=evidence_needed,
        )

# Backwards compatibility alias
FactCheckerMistralAdapter = FactCheckerQwenAdapter
FactCheckerModelAdapter = FactCheckerQwenAdapter  # New generic name

