"""High-accuracy editorial assessor for the Chief Editor agent (Qwen)."""

from __future__ import annotations

import json
import os
import textwrap
from typing import Any

from agents.common.openai_adapter import OpenAIAdapter
from common.observability import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the JustNews chief editor. Review provided copy and respond with JSON "
    "containing: priority (urgent|high|medium|low|review), stage (intake|analysis|fact_check|"
    "synthesis|review|publish|archive), confidence (0-1), summary, risk_flags (list), "
    "next_actions (list) and notes. Be concise and actionable."
)

class ChiefEditorModelAdapter:
    def __init__(self) -> None:
        disable_qwen = os.environ.get("CHIEF_EDITOR_DISABLE_QWEN", "0")
        self.enabled = str(disable_qwen).lower() not in {"1", "true"}

        base_url = (
            os.environ.get("VLLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("OPENAI_API_BASE")
        )
        if not base_url:
            vllm_host = os.environ.get("VLLM_HOST", "vllm")
            vllm_port = os.environ.get("VLLM_PORT", "8010")
            base_url = f"http://{vllm_host}:{vllm_port}/v1"

        self.adapter = OpenAIAdapter(
            name="chief_editor_qwen",
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            base_url=base_url,
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            system_prompt=SYSTEM_PROMPT,
            temperature=0.15,
            max_tokens=800,
            timeout=45.0,
        )

        if self.enabled:
            try:
                self.adapter.load()
            except Exception as e:
                logger.warning(f"Chief Editor Qwen adapter load failed: {e}")

    def review_content(
        self, content: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Original review method for full editorial decision support"""
        if not self.enabled:
            return None

        text = textwrap.shorten(content or "", width=7000, placeholder="...")
        meta = metadata or {}
        assignment = meta.get("assignment") or meta.get("topic")
        lead = f"Assignment: {assignment}\n" if assignment else ""
        user_block = f"{lead}Metadata: {json.dumps(meta, default=str)}\nCopy:\n'''{text}'''\n\nReturn valid JSON."

        try:
            self.adapter.ensure_loaded()
            result = self.adapter.infer(user_block)
            return self._parse_response(result.get("text", ""))
        except Exception as e:
            logger.warning(f"Chief Editor Qwen generation failed: {e}")
            return None

    def perform_task(self, task: str, content: str, context: str = "") -> dict[str, Any] | str | None:
        """Perform specific editorial task using LLM."""
        if not self.enabled:
            return None

        text = textwrap.shorten(content or "", width=4000, placeholder="...")

        prompts = {
            "quality": (
                "Assess the quality of this text. Return JSON with: "
                "overall_quality (0.0-1.0), assessment (high|medium|low), reasoning."
            ),
            "categorize": (
                "Categorize this text into exactly one of these categories: "
                "world, uk, business, politics, health, science, technology, entertainment, sport. "
                "Prefer the most specific category that is directly supported by the text. "
                "Return strict JSON only with keys: category (one of the allowed values), confidence (0.0-1.0)."
            ),
            "sentiment": (
                "Analyze the editorial sentiment/tone. Return JSON with: "
                "sentiment (positive|negative|neutral), confidence (0.0-1.0), editorial_tone (string)."
            ),
            "commentary": (
                f"Write a brief editorial commentary/summary for this {context}. "
                "Return only the commentary text, no JSON."
            )
        }

        user_prompt = f"{prompts.get(task, task)}\n\nText:\n'''{text}'''"

        try:
            self.adapter.ensure_loaded()
            # Override system prompt? OpenAIAdapter doesn't support easy per-call system prompt override
            # without re-init, but we can rely on the general persona or just strong user prompting.
            # The default system prompt is broad enough ("You are the chief editor").

            result = self.adapter.infer(user_prompt)
            output = result.get("text", "").strip()

            if task == "commentary":
                return output

            return self._parse_response(output)

        except Exception as e:
            logger.warning(f"Chief Editor Qwen task {task} failed: {e}")
            return None

    def _parse_response(self, text: str) -> dict[str, Any] | None:
        clean = text.replace("```json", "").replace("```", "").strip()
        if clean.startswith("[DRYRUN-openai:"):
            return {
                "priority": "medium",
                "stage": "review",
                "confidence": 0.75,
                "assessment": "Dry-run simulated chief editor review.",
                "risk_flags": [],
                "next_actions": ["Proceed to standard editorial review"],
                "notes": "Qwen dry-run compatibility payload",
            }
        try:
            return json.loads(clean)
        except Exception:
            return None


