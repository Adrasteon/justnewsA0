"""LLM-backed chain-of-thought helper for the Reasoning agent (Qwen)."""

from __future__ import annotations

import json
import os
import textwrap
from typing import Any

from agents.common.openai_adapter import OpenAIAdapter
from common.observability import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the JustNews reasoning specialist. Given domain facts and a query, "
    "produce structured JSON with keys: hypothesis, chain_of_thought (list of steps), "
    "verdict (supported|refuted|unclear), confidence (0-1), follow_up_questions (list)."
)

class ReasoningModelAdapter:
    def __init__(self) -> None:
        self.enabled = os.environ.get("REASONING_DISABLE_MISTRAL", "0").lower() not in {"1", "true"}

        self.adapter = OpenAIAdapter(
            name="reasoning_qwen",
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=700,
            timeout=45.0,
        )

    def analyze(
        self, query: str, context_facts: list[str] | None = None
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        facts_block = "\n".join(context_facts or [])
        user_block = f"Question: {query}\nFacts:\n{textwrap.shorten(facts_block, width=8000, placeholder='...') or 'None provided'}\n\nReturn valid JSON."

        try:
            self.adapter.ensure_loaded()
            result = self.adapter.infer(user_block)
            return self._parse_response(result.get("text", ""))
        except Exception as e:
            logger.warning(f"Reasoning Qwen generation failed: {e}")
            return None

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        clean = text.replace("```json", "").replace("```", "").strip()
        if clean.startswith("[DRYRUN-openai:"):
            return {
                "hypothesis": "Dry-run hypothesis",
                "chain_of_thought": ["Step 1", "Step 2"],
                "verdict": "unclear",
                "confidence": 0.7,
                "follow_up_questions": ["What additional evidence is available?"],
            }
        try:
            return json.loads(clean)
        except Exception:
            return None

# Alias for compat
ReasoningMistralAdapter = ReasoningModelAdapter

