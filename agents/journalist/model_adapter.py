"""LLM helper for the Journalist agent backed by the Qwen adapter."""

from __future__ import annotations

import json
import os
import textwrap
from typing import Any

from agents.common.openai_adapter import OpenAIAdapter
from common.observability import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the JustNews field journalist assistant. Given freshly crawled "
    "content, produce a concise JSON brief with keys: headline, summary, "
    "key_points (list of bullet strings), leads (list), follow_up_questions "
    "(list), and risk_flags (list). Keep the tone factual and actionable."
)

class JournalistModelAdapter:
    def __init__(self) -> None:
        self.enabled = os.environ.get("JOURNALIST_DISABLE_MISTRAL", "0").lower() not in {"1", "true"}

        self.adapter = OpenAIAdapter(
            name="journalist_qwen",
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            system_prompt=SYSTEM_PROMPT,
            temperature=0.25,
            max_tokens=700,
            timeout=45.0,
        )

    def generate_story_brief(
        self,
        markdown: str | None,
        html: str | None = None,
        *,
        url: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None

        content = markdown or html or ""
        trimmed = textwrap.shorten(content, width=8000, placeholder="...")

        if not trimmed:
            return None

        title_line = f"Title: {title}\n" if title else ""
        user_block = f"{title_line}URL: {url or 'unknown'}\nContent:\n'''{trimmed}'''\n\nReturn valid JSON."

        try:
            self.adapter.ensure_loaded()
            result = self.adapter.infer(user_block)
            doc = self._parse_response(result.get("text", ""))

            if doc and url:
                doc.setdefault("url", url)
            return doc
        except Exception as e:
            logger.warning(f"Journalist Qwen generation failed: {e}")
            return None

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        clean = text.replace("```json", "").replace("```", "").strip()
        if clean.startswith("[DRYRUN-openai:"):
            return {
                "headline": "Dry-run headline",
                "summary": "Dry-run simulated journalist brief.",
                "key_points": ["Point A", "Point B"],
                "leads": ["Lead 1"],
                "follow_up_questions": ["What additional source confirms this?"],
                "risk_flags": [],
            }
        try:
            return json.loads(clean)
        except Exception:
            return None

# Alias for compat
JournalistMistralAdapter = JournalistModelAdapter

