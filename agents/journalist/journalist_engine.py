"""
Journalist engine - Crawl4AI-backed discovery and AI-enhanced page reader

This engine is intentionally lightweight and delegates crawling to a local
Crawl4AI server (systemd managed) via a bridge. It exposes a small async API
that mirrors scout responsibilities but centralizes heavy LLM & browser work
in a separate process.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

from agents.c4ai.bridge import crawl_via_local_server
from agents.journalist.model_adapter import JournalistModelAdapter
from common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class JournalistConfig:
    """Configuration for JournalistEngine with env-driven defaults.

    Environment variables consulted:
    - CRAWL4AI_HOST (default 127.0.0.1)
    - CRAWL4AI_PORT (default 3308)
    - CRAWL4AI_USE_LLM (optional, 'true'/'false')
    """

    crawl4ai_base_url: str = (
        os.getenv("CRAWL4AI_BASE_URL")
        or f"http://{os.getenv('CRAWL4AI_HOST', '127.0.0.1')}:{os.getenv('CRAWL4AI_PORT', '3308')}"
    )
    default_mode: str = "standard"
    use_llm_extraction: bool = os.getenv("CRAWL4AI_USE_LLM", "true").lower() in (
        "1",
        "true",
        "yes",
    )


class JournalistEngine:
    def __init__(self, config: JournalistConfig | None = None):
        self.config = config or JournalistConfig()
        self._shutdown = False
        # Use shared ModelAdapter (Qwen backed) for consistent behavior
        self._model_adapter = JournalistModelAdapter()

    async def crawl_and_analyze(
        self, url: str, mode: str | None = None
    ) -> dict[str, Any]:
        mode = mode or self.config.default_mode
        # Use the bridge helper to call the local Crawl4AI server
        results = await crawl_via_local_server(
            url, mode=mode, use_llm=self.config.use_llm_extraction
        )
        if self.config.use_llm_extraction:
            brief = await asyncio.to_thread(self._generate_llm_brief, results)
            if brief:
                results = dict(results)
                results["llm_brief"] = brief
        return results

    async def shutdown(self) -> None:
        self._shutdown = True
        # Perform any graceful cleanup here (if needed)
        await asyncio.sleep(0)

    # Internal helpers -----------------------------------------------------
    def _generate_llm_brief(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not payload or not getattr(self, "_model_adapter", None):
            return None
        try:
            markdown = payload.get("markdown") if isinstance(payload, dict) else None
            html = payload.get("html") if isinstance(payload, dict) else None
            title = payload.get("title") if isinstance(payload, dict) else None
            url = payload.get("url") if isinstance(payload, dict) else None
            
            result = self._model_adapter.generate_story_brief(
                markdown, html, url=url, title=title
            )

            # Collect prediction for training
            try:
                from training_system import collect_prediction
                collect_prediction(
                    agent_name="journalist",
                    task_type="generate_story_brief",
                    input_text=f"Title: {title}\nURL: {url}\nContent: {markdown[:2000] if markdown else 'No markdown content'}",
                    prediction=result,
                    confidence=1.0,  # Qwen doesn't provide confidence yet
                    source_url=url or "",
                )
                logger.debug("📊 Training data collected for story brief generation")
            except ImportError:
                pass  # Training system not available
            except Exception as e:
                logger.warning(f"Failed to collect training data: {e}")

            return result
        except Exception as exc:
            logger.debug("Journalist model adapter failed: %s", exc)
            return None
