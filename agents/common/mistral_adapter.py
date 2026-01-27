from __future__ import annotations

import json
import logging
import os
from typing import Any

from .adapter_base import AdapterError, BaseAdapter
from .openai_adapter import OpenAIAdapter

logger = logging.getLogger(__name__)

class MistralAdapter(BaseAdapter):
    """
    shim-adapter for v4.0.0 migration:
    Redirects legacy 'MistralAdapter' calls to the centralized Qwen/vLLM instance
    via OpenAI-compatible API.
    """

    def __init__(
        self,
        *,
        agent: str,
        adapter_name: str,
        system_prompt: str = "",
        disable_env: str = "",
    ) -> None:
        super().__init__(name=f"mistral-shim:{agent}")
        self.agent = agent
        self.adapter_name = adapter_name
        self.system_prompt = system_prompt or ""
        self.disable_env = disable_env or f"{agent.upper()}_DISABLE_MISTRAL"

        # Read vLLM config
        self.vllm_base_url = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8010/v1")
        self.vllm_api_key = os.environ.get("VLLM_API_KEY", "unused")
        self.vllm_model = os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ")

        # Instantiate the actual worker
        self.openai = OpenAIAdapter(
            api_key=self.vllm_api_key,
            base_url=self.vllm_base_url,
            model=self.vllm_model,
            system_prompt=self.system_prompt,
        )

        # self.openai.load() is called later in self.load()

        self._agent_impl: object | None = None
        # Try to eager-populate a per-agent implementation if available.
        try:
            # Candidate module names to try for agent-specific helpers
            candidates = [
                f"agents.{self.agent}.mistral_adapter",
                f"agents.tools.mistral_{self.agent}_adapter",
                "agents.tools.mistral_re_ranker_adapter",
            ]
            for module_name in candidates:
                try:
                    mod = __import__(module_name, fromlist=["*"])
                    parts = [p.capitalize() for p in self.agent.split("_")]
                    class_name = "".join(parts) + "MistralAdapter"
                    cls = getattr(mod, class_name, None)
                    if cls:
                        try:
                            self._agent_impl = cls()
                            break
                        except Exception:
                            self._agent_impl = None
                except Exception:
                    continue
        except Exception:
            self._agent_impl = None

        # Dry run logic
        env_dry_run = (
            os.environ.get("MODEL_STORE_DRY_RUN") == "1"
            or os.environ.get("DRY_RUN") == "1"
        )
        self._dry_run = self.dry_run or env_dry_run
        if self._dry_run:
            self.openai.dry_run = True

    def load(self, model_id: str | None = None, config: dict | None = None) -> None:
        """Connect to vLLM (check health)."""
        try:
            self.openai.load()
            self.mark_loaded()
            logger.info(f"MistralAdapter (Shim) connected to vLLM: {self.vllm_model}")
        except Exception as e:
            raise AdapterError(f"vllm-connection-failed: {e}")

    def infer(self, prompt: str, **kwargs: Any) -> dict:
        """Forward inference to vLLM/OpenAI."""
        return self.openai.infer(prompt, **kwargs)

    def summarize_cluster(
        self, articles: list[str], context: str | None = None
    ) -> dict | None:
        """Shim methodology for clustering using the shared LLM."""
        if self._dry_run:
             return {
                "summary": f"[DRYRUN] Summary for {len(articles)} articles",
                "key_points": ["Point A", "Point B"],
                "confidence": 0.9
            }

        prompt = f"Summarize these {len(articles)} articles."
        if context:
            prompt += f" Context: {context}"

        joined = "\n\n".join(articles[:5]) # Limit context
        prompt += f"\n\nArticles:\n{joined}"

        # Simplified logic: just ask for JSON
        res = self.infer(prompt + "\n\nProvide output in valid JSON with keys: summary, key_points, confidence.")
        text = res["text"]
        try:
            # Basic cleanup
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except:
             logger.warning(f"Failed to parse JSON from vLLM shim: {text[:100]}")
             return None

    def batch_infer(self, prompts: list[str], **kwargs: Any) -> list[dict]:
        return [self.infer(p, **kwargs) for p in prompts]

    def __getattr__(self, name: str):
        # Delegate unknown attribute access to per-agent implementation if present.
        try:
            agent_impl = object.__getattribute__(self, "_agent_impl")
        except AttributeError:
            agent_impl = None
        if agent_impl and hasattr(agent_impl, name):
            return getattr(agent_impl, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

        if agent_impl is not None:
            # Guard against accidentally delegating to the same object instance
            # to avoid self-referential loops.
            if agent_impl is self:
                raise AttributeError(name)
            attr = getattr(agent_impl, name, None)
            if attr is not None:
                return attr
        raise AttributeError(name)

    # Agent-friendly helpers ----------------------------------------------
    def classify(self, text: str) -> object | None:
        """Analyst-style classifier that returns a normalized sentiment/bias structure.

        If a per-agent implementation is available we delegate to it; otherwise
        we use the base JSON adapter / dry-run simulated payload.
        """
        if not text or not text.strip():
            return None

        # Dry-run short-circuit: avoid calling per-agent tokenizers which may
        # not be callable in dry-run mode (tokenizer returned as dict).
        if self._dry_run or (
            self._base is not None
            and isinstance(self._base.model, dict)
            and self._base.model.get("dry_run")
        ):
            # Return a minimal compatible object similar to Analyst.AdapterResult
            from types import SimpleNamespace

            sentiment = {
                "dominant_sentiment": "neutral",
                "confidence": 0.75,
                "intensity": "mild",
                "sentiment_scores": {"positive": 0.4, "negative": 0.3, "neutral": 0.3},
                "method": "mistral_adapter",
                "model_name": self.adapter_name,
            }
            bias = {
                "has_bias": False,
                "bias_score": 0.2,
                "bias_level": "minimal",
                "confidence": 0.7,
                "method": "mistral_adapter",
            }
            return SimpleNamespace(
                sentiment=sentiment, bias=bias, raw={"simulated": True}
            )

        # Real path: format and send the messages through the base helper
        snippet = (text or "").strip()
        if not snippet:
            return None

        # If base isn't loaded, still allow the dry-run or simulated path above.
        if not self._base:
            # can't call into the base for real inference; treat as unavailable
            return None

        user_block = f"Text to evaluate:\n'''{self._base._truncate_content(snippet)}'''"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        doc = self._base._chat_json(messages)
        if not doc:
            return None

        # Return the raw payload — tests / callers expect a structure similar to per-agent's AdapterResult
        return (
            getattr(self, "_agent_impl", None)
            and getattr(self._agent_impl, "_normalize", lambda p, e=None: p)(doc, 0.0)
            or doc
        )

    def generate_story_brief(
        self,
        markdown: str | None,
        html: str | None = None,
        *,
        url: str | None = None,
        title: str | None = None,
    ):
        if not markdown and not html:
            return None
        # Dry-run early short-circuit
        if self._dry_run or (
            self._base is not None
            and isinstance(self._base.model, dict)
            and self._base.model.get("dry_run")
        ):
            return {
                "headline": f"Simulated brief for {title or url or 'content'}",
                "summary": "Simulated summary",
                "url": url,
            }

        # Fallback to base JSON chat
        content = markdown or html or ""
        trimmed = self._base._truncate_content(content)
        if not trimmed:
            return None
        title_line = f"Title: {title}\n" if title else ""
        user_block = f"{title_line}URL: {url or 'unknown'}\nContent:\n'''{trimmed}'''"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        doc = self._base._chat_json(messages)
        if doc and url:
            doc.setdefault("url", url)
        return doc

    def review(self, content: str, url: str | None = None):
        if not content or not content.strip():
            return None

        if self._dry_run or (
            self._base is not None
            and isinstance(self._base.model, dict)
            and self._base.model.get("dry_run")
        ):
            # Simulated critic assessment
            from types import SimpleNamespace

            return SimpleNamespace(
                quality=0.6,
                bias=0.3,
                consistency=0.5,
                readability=0.7,
                originality=0.6,
                overall=0.6,
                assessment="Simulated critique.",
                recommendations=["Rewrite headline", "Add sources"],
            )

        if not self._base._ensure_loaded():
            return None

        trimmed = self._base._truncate_content(content)
        url_line = f"\nSource: {url}" if url else ""
        user_block = f"Article:\n'''{trimmed}'''{url_line}"
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        doc = self._base._chat_json(messages)
        return getattr(self, "_agent_impl", None) and getattr(
            self._agent_impl, "_normalize", lambda p: p
        )(doc)

    def evaluate_claim(self, claim: str, context: str | None = None):
        if not claim or not claim.strip():
            return None
        if self._dry_run or (
            self._base is not None
            and isinstance(self._base.model, dict)
            and self._base.model.get("dry_run")
        ):
            from types import SimpleNamespace

            return SimpleNamespace(
                verdict="unclear",
                confidence=0.6,
                score=0.6,
                rationale="Simulated",
                evidence_needed=False,
            )

        if not self._base._ensure_loaded():
            return None

        context_block = f"\nContext:\n{context}" if context else ""
        user_block = (
            f"Claim:\n'''{self._base._truncate_content(claim)}'''{context_block}"
        )
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        doc = self._base._chat_json(messages)
        return getattr(self, "_agent_impl", None) and getattr(
            self._agent_impl, "_normalize", lambda p: p
        )(doc)

    # Convenience compatibility: some per-agent adapters expose different
    # method names like `analyze` (reasoning) or `review_content` (chief editor).
    def analyze(
        self, query: str, context_facts: list[str] | None = None
    ) -> dict | None:
        # Delegate if implementation exists
        # Dry-run first
        if self._dry_run or (
            self._base is not None
            and isinstance(self._base.model, dict)
            and self._base.model.get("dry_run")
        ):
            return {
                "hypothesis": "Simulated hypothesis",
                "chain_of_thought": ["Step 1", "Step 2"],
                "verdict": "unclear",
                "confidence": 0.65,
                "follow_up_questions": ["What source supports X?"],
            }

        if not self._base:
            return None

        try:
            return (
                self._agent_impl.analyze(query, context_facts)
                if getattr(self, "_agent_impl", None)
                and hasattr(self._agent_impl, "analyze")
                else None
            )
        except Exception:
            return None

    def review_content(self, content: str, metadata: dict | None = None) -> dict | None:
        # delegate to per-agent implementation if available
        if getattr(self, "_agent_impl", None) and hasattr(
            self._agent_impl, "review_content"
        ):
            try:
                val = self._agent_impl.review_content(content, metadata)
                if val is not None:
                    return val
            except Exception:
                pass

        # fallback to review method and return dict form
        res = self.review(content, None)
        if res is None:
            return None

        try:
            # convert SimpleNamespace or object to dict when possible
            if hasattr(res, "__dict__"):
                return dict(res.__dict__)
            return dict(res)
        except Exception:
            return {"assessment": str(res)}

    def health_check(self) -> dict:
        status = super().health_check()
        available = bool(self._base and getattr(self._base, "is_available", False))
        status.update(
            {
                "available": available,
                "load_error": getattr(self._base, "_load_error", None),
                "agent": self.agent,
                "adapter_name": self.adapter_name,
            }
        )
        return status

    def unload(self) -> None:
        if self._base is not None:
            try:
                self._base.model = None
                self._base.tokenizer = None
            except Exception:
                pass
        self.mark_unloaded()

    def metadata(self) -> dict:
        return {
            "agent": self.agent,
            "adapter": self.adapter_name,
            "dry_run": self._dry_run,
        }
