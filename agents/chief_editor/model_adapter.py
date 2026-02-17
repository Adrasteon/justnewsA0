"""High-accuracy editorial assessor for the Chief Editor agent (Qwen)."""

from __future__ import annotations
import os
import json
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
        
        self.adapter = OpenAIAdapter(
            name="chief_editor_qwen",
            model=os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"),
            base_url=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1"),
            api_key=os.environ.get("VLLM_API_KEY", "unused"),
            system_prompt=SYSTEM_PROMPT,
            temperature=0.15,
            max_tokens=380,
            timeout=45.0
        )

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
                "Categorize this text into one news category (e.g. Politics, Technology, distinct). "
                "Return JSON with: category (string), confidence (0.0-1.0)."
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
        try:
            clean = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except Exception:
            return None


