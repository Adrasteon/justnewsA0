from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from common.observability import get_logger

from .openai_adapter import OpenAIAdapter

logger = get_logger(__name__)


class TriageAdapter:
    """First-class ingestion triage adapter with model-store integration."""

    _adapter_cache: dict[str, OpenAIAdapter] = {}

    def __init__(
        self,
        *,
        name: str,
        agent: str = 'crawler_triage',
        adapter_name: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.name = name
        self.agent = agent
        self.adapter_name = (
            adapter_name
            or os.environ.get('CRAWL4AI_TRIAGE_ADAPTER_NAME')
            or 'qwen2_crawler_triage_v1'
        )
        self.strict_model_store = str(os.environ.get('STRICT_MODEL_STORE', '0')).strip().lower() in {
            '1',
            'true',
            'yes',
            'on',
        }
        self.model = model or os.environ.get('CRAWL4AI_TRIAGE_MODEL')
        self.timeout = float(timeout or os.environ.get('CRAWL4AI_AI_TRIAGE_TIMEOUT_SEC', '8'))

    @staticmethod
    def is_enabled() -> bool:
        return str(os.environ.get('CRAWL4AI_AI_TRIAGE_ENABLED', '0')).strip().lower() in {
            '1',
            'true',
            'yes',
            'on',
        }

    @staticmethod
    def resolve_vllm_base_url() -> str:
        explicit = os.environ.get('VLLM_BASE_URL') or os.environ.get('VLLM_API_BASE')
        if explicit:
            return explicit.rstrip('/')

        host = os.environ.get('VLLM_HOST', 'vllm').strip() or 'vllm'
        port = str(os.environ.get('VLLM_PORT', '8010')).strip() or '8010'
        return f'http://{host}:{port}/v1'

    def get_llm_adapter(self) -> OpenAIAdapter | None:
        if not self.is_enabled():
            return None

        resolved_model, metadata = self._resolve_model_and_metadata()
        cache_key = f'{self.name}:{resolved_model}:{self.adapter_name}'

        cached = self._adapter_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            extra_headers = self._build_extra_headers(metadata)
            adapter = OpenAIAdapter(
                name=self.name,
                model=resolved_model,
                base_url=self.resolve_vllm_base_url(),
                api_key=os.environ.get('VLLM_API_KEY', 'unused'),
                system_prompt=(
                    'You are an ingestion triage classifier for a news pipeline. '
                    'Return strict JSON with deterministic labels.'
                ),
                temperature=0.0,
                max_tokens=220,
                timeout=self.timeout,
                max_retries=1,
                extra_headers=extra_headers,
            )
            adapter.ensure_loaded()
            self._adapter_cache[cache_key] = adapter
            return adapter
        except Exception as exc:
            logger.debug('Triage adapter unavailable, fallback will be used: %s', exc)
            self._adapter_cache.pop(cache_key, None)
            return None

    def _resolve_model_and_metadata(self) -> tuple[str, dict[str, Any] | None]:
        metadata = self._resolve_model_store_metadata()
        if self.model:
            return self.model, metadata

        if metadata and self._vllm_lora_enabled():
            return self.adapter_name, metadata

        if metadata:
            base_info = metadata.get('base_info') if isinstance(metadata, dict) else None
            if isinstance(base_info, dict):
                hf_id = str(base_info.get('hf_id') or '').strip()
                if hf_id:
                    return hf_id, metadata

        return os.environ.get('VLLM_MODEL', 'Qwen/Qwen2.5-14B-Instruct-AWQ'), metadata

    @staticmethod
    def _vllm_lora_enabled() -> bool:
        raw = str(os.environ.get('VLLM_ENABLE_LORA', 'true')).strip().lower()
        return raw in {'1', 'true', 'yes', 'on'}

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
                metadata.get('adapter_path') if isinstance(metadata, dict) else None
            )

            if self.strict_model_store and adapter_path is None:
                raise RuntimeError(
                    'STRICT_MODEL_STORE=1 but triage adapter path is missing '
                    f'for agent={self.agent} adapter={self.adapter_name}'
                )

            if isinstance(metadata, dict) and adapter_path is not None:
                metadata = dict(metadata)
                metadata['adapter_path'] = adapter_path

            return metadata
        except Exception as exc:
            if self.strict_model_store:
                raise
            logger.debug(
                'Triage adapter model-store metadata unavailable for %s/%s: %s',
                self.agent,
                self.adapter_name,
                exc,
            )
            return None

    def _build_extra_headers(self, metadata: dict[str, Any] | None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if metadata and isinstance(metadata, dict):
            adapter_path = metadata.get('adapter_path')
            if adapter_path:
                headers['x-justnews-adapter-path'] = str(adapter_path)
            headers['x-justnews-adapter-name'] = self.adapter_name
        return headers

    @staticmethod
    def _extract_json_payload(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        clean = text.replace('```json', '```').strip()
        if clean.startswith('```') and clean.endswith('```'):
            clean = clean[3:-3].strip()

        try:
            parsed = json.loads(clean)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            match = re.search(r'\{[\s\S]*\}', clean)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None

    def classify_page(self, url: str, title: str, content: str) -> dict[str, Any] | None:
        adapter = self.get_llm_adapter()
        if adapter is None:
            return None

        snippet = (content or '')[:2600]
        prompt = (
            'Classify whether this web page should be ingested as a news article. '
            'Return JSON only with keys: decision, confidence, page_type, reason_codes. '
            'decision must be one of accept,reject,quarantine. '
            'reason_codes must be a short list of machine-friendly strings.\n\n'
            f'URL: {url}\n'
            f'Title: {title}\n'
            f'Content snippet:\n{snippet}'
        )

        try:
            result = adapter.infer(prompt)
        except Exception as exc:
            logger.debug('Triage adapter infer failed for %s: %s', url, exc)
            return None

        parsed = self._extract_json_payload(str(result.get('text') or '').strip())
        if not isinstance(parsed, dict):
            return None

        decision = str(parsed.get('decision') or '').strip().lower()
        if decision not in {'accept', 'reject', 'quarantine'}:
            return None

        try:
            confidence = float(parsed.get('confidence', 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = min(1.0, max(0.0, confidence))

        reason_codes = [
            str(item).strip().lower().replace(' ', '_')
            for item in (parsed.get('reason_codes') or [])
            if str(item).strip()
        ]

        return {
            'decision': decision,
            'confidence': confidence,
            'reason_codes': reason_codes or ['ai_triage_no_reason'],
            'page_type': str(parsed.get('page_type') or '').strip().lower() or None,
        }
