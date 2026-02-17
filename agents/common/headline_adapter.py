from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from common.observability import get_logger

from .openai_adapter import OpenAIAdapter

logger = get_logger(__name__)


class HeadlineAdapter:
    """First-class headline generation adapter with safety and training hooks."""

    _adapter_cache: dict[str, OpenAIAdapter] = {}

    def __init__(
        self,
        *,
        name: str,
        agent: str = "chief_editor",
        adapter_name: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.name = name
        self.agent = agent
        self.adapter_name = (
            adapter_name
            or os.environ.get("TITLE_HYBRID_ADAPTER_NAME")
            or os.environ.get("HEADLINE_ADAPTER_NAME")
            or "qwen2_headline_v1"
        )
        self.strict_model_store = str(os.environ.get("STRICT_MODEL_STORE", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.model = model or os.environ.get("TITLE_HYBRID_MODEL")
        self.timeout = float(timeout or os.environ.get("TITLE_HYBRID_LLM_TIMEOUT", "8"))

    @staticmethod
    def is_enabled() -> bool:
        return str(os.environ.get("TITLE_HYBRID_LLM_ENABLED", "true")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def resolve_vllm_base_url() -> str:
        explicit = os.environ.get("VLLM_BASE_URL") or os.environ.get("VLLM_API_BASE")
        if explicit:
            return explicit.rstrip("/")

        host = os.environ.get("VLLM_HOST", "vllm").strip() or "vllm"
        port = str(os.environ.get("VLLM_PORT", "8010")).strip() or "8010"
        return f"http://{host}:{port}/v1"

    def get_llm_adapter(self) -> OpenAIAdapter | None:
        if not self.is_enabled():
            return None

        resolved_model, metadata = self._resolve_model_and_metadata()
        cache_key = f"{self.name}:{resolved_model}:{self.adapter_name}"

        cached = self._adapter_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            extra_headers = self._build_extra_headers(metadata)
            adapter = OpenAIAdapter(
                name=self.name,
                model=resolved_model,
                base_url=self.resolve_vllm_base_url(),
                api_key=os.environ.get("VLLM_API_KEY", "unused"),
                system_prompt=(
                    "You are a newsroom headline editor. Write neutral, factual, non-sensational headlines. "
                    "Do not use emotional language, opinion, exaggeration, or clickbait."
                ),
                temperature=0.05,
                max_tokens=120,
                timeout=self.timeout,
                max_retries=1,
                extra_headers=extra_headers,
            )
            adapter.ensure_loaded()
            self._adapter_cache[cache_key] = adapter
            return adapter
        except Exception as exc:
            logger.debug(f"Headline adapter unavailable, falling back to deterministic flow: {exc}")
            self._adapter_cache.pop(cache_key, None)
            return None

    def _resolve_model_and_metadata(self) -> tuple[str, dict[str, Any] | None]:
        metadata = self._resolve_model_store_metadata()
        if self.model:
            return self.model, metadata

        if metadata and self._vllm_lora_enabled():
            return self.adapter_name, metadata

        if metadata:
            base_info = metadata.get("base_info") if isinstance(metadata, dict) else None
            if isinstance(base_info, dict):
                hf_id = str(base_info.get("hf_id") or "").strip()
                if hf_id:
                    return hf_id, metadata

        return os.environ.get("VLLM_MODEL", "Qwen/Qwen2.5-14B-Instruct-AWQ"), metadata

    @staticmethod
    def _vllm_lora_enabled() -> bool:
        raw = str(os.environ.get("VLLM_ENABLE_LORA", "true")).strip().lower()
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _resolve_existing_path(raw_path: Any) -> Path | None:
        if raw_path is None:
            return None
        try:
            candidate = Path(str(raw_path))
        except Exception:
            return None
        return candidate if candidate.exists() else None

    def _resolve_model_store_metadata(self) -> dict[str, Any] | None:
        try:
            from agents.common.model_loader import get_agent_model_metadata

            metadata = get_agent_model_metadata(self.agent, self.adapter_name)
            adapter_path = self._resolve_existing_path(
                metadata.get("adapter_path") if isinstance(metadata, dict) else None
            )

            if self.strict_model_store and adapter_path is None:
                raise RuntimeError(
                    "STRICT_MODEL_STORE=1 but headline adapter path is missing "
                    f"for agent={self.agent} adapter={self.adapter_name}"
                )

            if isinstance(metadata, dict) and adapter_path is not None:
                metadata = dict(metadata)
                metadata["adapter_path"] = adapter_path

            return metadata
        except Exception as exc:
            if self.strict_model_store:
                raise
            logger.debug(
                "Headline adapter model-store metadata unavailable for %s/%s: %s",
                self.agent,
                self.adapter_name,
                exc,
            )
            return None

    def _build_extra_headers(self, metadata: dict[str, Any] | None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if metadata and isinstance(metadata, dict):
            adapter_path = metadata.get("adapter_path")
            if adapter_path:
                headers["x-justnews-adapter-path"] = str(adapter_path)
            headers["x-justnews-adapter-name"] = self.adapter_name
        return headers

    @staticmethod
    def extract_candidate_lines(raw_text: str) -> list[str]:
        cleaned = (raw_text or "").replace("```json", "").replace("```", "").strip()
        candidates: list[str] = []

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                values = parsed.get("headlines") or parsed.get("titles") or []
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, str) and item.strip():
                            candidates.append(item.strip())
            elif isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, str) and item.strip():
                        candidates.append(item.strip())
        except Exception:
            pass

        if candidates:
            return candidates

        for line in cleaned.splitlines():
            normalized = re.sub(r"^\s*(?:[-*\d.)]+\s*)", "", line).strip()
            if normalized:
                candidates.append(normalized)

        return candidates

    @staticmethod
    def is_sensational(text: str) -> bool:
        lowered = (text or "").lower()
        banned_fragments = (
            "shocking",
            "bombshell",
            "explosive",
            "jaw-dropping",
            "you won't believe",
            "stuns",
            "slams",
            "devastating",
            "unbelievable",
            "must-see",
        )
        if any(fragment in lowered for fragment in banned_fragments):
            return True
        return "!" in lowered or "?" in lowered

    @staticmethod
    def is_invalid_format(text: str) -> bool:
        candidate = (text or "").strip().lower()
        if not candidate:
            return True
        if "\n" in candidate:
            return True
        return any(token in candidate for token in ('"headlines"', "{", "}", "[", "]"))

    @staticmethod
    def _strip_generic_lede(text: str) -> str:
        patterns = [
            r"^the article (discusses|explores|examines|highlights|focuses on|covers|reports on)\s+",
            r"^this article (discusses|explores|examines|highlights|focuses on|covers|reports on)\s+",
            r"^the report (discusses|explores|examines|highlights|focuses on|covers|reports on)\s+",
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip()

    @staticmethod
    def _trim_trailing_stopwords(text: str) -> str:
        stopwords = {
            "a",
            "an",
            "the",
            "and",
            "or",
            "but",
            "of",
            "to",
            "in",
            "on",
            "for",
            "with",
            "from",
            "by",
            "at",
        }
        words = text.split()
        while words and words[-1].lower().strip(".,;:!?") in stopwords:
            words.pop()
        return " ".join(words).strip()

    @staticmethod
    def _capitalize_headline(text: str) -> str:
        if not text:
            return ""
        first_char = text[0]
        if first_char.isalpha():
            return first_char.upper() + text[1:]
        return text

    @staticmethod
    def _fit_length(text: str, max_chars: int = 190) -> str:
        candidate = (text or "").strip()
        if len(candidate) <= max_chars:
            return candidate

        punctuation_positions = [
            candidate.rfind(",", 0, max_chars),
            candidate.rfind(";", 0, max_chars),
            candidate.rfind(":", 0, max_chars),
            candidate.rfind(" - ", 0, max_chars),
            candidate.rfind(" — ", 0, max_chars),
            candidate.rfind(" – ", 0, max_chars),
        ]
        cut_at = max(punctuation_positions)
        if cut_at >= 18:
            return candidate[:cut_at].rstrip(" ,.;:-")

        words = candidate.split()
        fitted_words: list[str] = []
        for word in words:
            tentative = " ".join(fitted_words + [word]).strip()
            if len(tentative) > max_chars:
                break
            fitted_words.append(word)
        return " ".join(fitted_words).rstrip(" ,.;:-")

    @staticmethod
    def headlineize(raw_text: Any, max_chars: int = 190) -> str:
        if not raw_text:
            return ""

        normalized = re.sub(r"\s+", " ", str(raw_text)).strip().strip('"\'')
        normalized = re.sub(r"^(headline|title)\s*:\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"^[\-–—:\s]+", "", normalized)
        if not normalized:
            return ""

        normalized = HeadlineAdapter._strip_generic_lede(normalized)
        if not normalized:
            return ""

        clause = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0].strip()

        if len(clause) > 160:
            for splitter in (r"\s+[–—-]\s+", r";", r"\|", r",\s+"):
                candidate = re.split(splitter, clause, maxsplit=1)[0].strip()
                if len(candidate) >= 25:
                    clause = candidate
                    break

        clause = HeadlineAdapter._trim_trailing_stopwords(clause)
        if clause and not re.search(r"[.!?…]$", clause):
            clause = clause.rstrip(" ,.;:-")

        clause = HeadlineAdapter._fit_length(clause, max_chars=max_chars)
        clause = HeadlineAdapter._trim_trailing_stopwords(clause)
        clause = HeadlineAdapter._capitalize_headline(clause)
        return re.sub(r"\s+", " ", clause).strip()

    def generate_candidates(self, context: str) -> list[str]:
        adapter = self.get_llm_adapter()
        if adapter is None:
            return []

        compact_context = (context or "").strip()
        if not compact_context:
            return []

        prompt = (
            "Create exactly 3 alternative headlines for the following news context.\n"
            "Rules:\n"
            "- Neutral, factual tone only\n"
            "- No sensational words, no emotional framing, no opinion\n"
            "- Plain statement style\n"
            "- 6 to 16 words\n"
            "- Do not use exclamation marks or questions\n"
            "- Return JSON only in this format: {\"headlines\": [\"...\", \"...\", \"...\"]}\n\n"
            f"Context:\n{compact_context[:1800]}"
        )

        try:
            response = adapter.infer(prompt)
            return self.extract_candidate_lines(str(response.get("text") or ""))
        except Exception as exc:
            logger.debug(f"Headline generation failed, using deterministic fallback: {exc}")
            return []

    @staticmethod
    def select_best_headline(
        candidates: list[Any],
        *,
        min_len: int = 10,
        disallowed_pattern: re.Pattern[str] | None = None,
    ) -> str:
        for candidate in candidates:
            headline = HeadlineAdapter.headlineize(candidate)
            if not headline:
                continue
            if HeadlineAdapter.is_invalid_format(headline):
                continue
            if HeadlineAdapter.is_sensational(headline):
                continue
            if disallowed_pattern and disallowed_pattern.match(headline):
                continue
            if len(headline) < min_len:
                continue
            return headline
        return ""

    @staticmethod
    def collect_training_example(
        *,
        input_text: str,
        prediction: dict[str, Any],
        confidence: float,
        source_url: str = "",
    ) -> None:
        try:
            from training_system import collect_prediction

            collect_prediction(
                agent_name="chief_editor",
                task_type="headline_generation",
                input_text=input_text,
                prediction=prediction,
                confidence=confidence,
                source_url=source_url,
            )
        except ImportError:
            logger.debug("Training system not available - skipping headline training collection")
        except Exception as exc:
            logger.warning(f"Failed to collect headline training example: {exc}")
