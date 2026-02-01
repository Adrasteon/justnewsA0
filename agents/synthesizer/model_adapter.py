"""LLM helper for the Synthesizer agent backed by the Qwen adapter."""

from __future__ import annotations
import os
import json
import textwrap
from typing import Any
from agents.common.openai_adapter import OpenAIAdapter
from common.observability import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the JustNews synthesis lead. Given multiple article snippets, "
    "produce JSON with summary, narrative_voice, key_points (list), cautions (list), "
    "and pull_quotes (list). Emphasize factual consistency and note any gaps."
)

class SynthesizerModelAdapter:
    def __init__(self) -> None:
        self.enabled = os.environ.get("SYNTHESIZER_DISABLE_QWEN", "0").lower() not in {"1", "true"}
        
        # Using the specific adapter ID 'qwen_synthesizer_v1' to enable training/refinement loops
        # that target this specific adapter configuration in model_store/synthesizer/adapters/qwen_synthesizer_v1
        self.adapter = OpenAIAdapter(
            name="qwen_synthesizer_v1",
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            # Force 'unused' to match the running vLLM instance configuration
            api_key="unused", # os.environ.get("VLLM_API_KEY") or "unused",
            system_prompt=SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=600,  # Slightly increased from legacy 512
            timeout=300.0
        )
        self.adapter.load()

    def summarize_cluster(
        self, articles: list[str], context: str | None = None
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        
        # Dynamic context window fitting (Target: ~40k chars for <16k tokens)
        target_total_chars = 40000
        per_article_limit = max(1000, target_total_chars // max(1, len(articles)))
        
        snippets = [
            textwrap.shorten(a, width=per_article_limit, placeholder="...") 
            for a in articles if a and a.strip()
        ]
        if not snippets:
            return None
            
        joined = "\n---\n".join(snippets)
        prefix = f"Context: {context}\n" if context else ""
        user_block = f"{prefix}Articles:\n'''{joined}'''\n\nReturn valid JSON."
        
        try:
            self.adapter.ensure_loaded()
            result = self.adapter.infer(user_block)
            return self._parse_response(result.get("text", ""))
        except Exception as e:
            logger.warning(f"Synthesizer Qwen generation failed: {e}")
            return None

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        try:
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception:
            return None

# Alias for compat
SynthesizerMistralAdapter = SynthesizerModelAdapter

