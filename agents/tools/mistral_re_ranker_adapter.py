"""Shared JSON adapter helper for the Mistral-powered re-ranker."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from agents.common.base_mistral_json_adapter import BaseMistralJSONAdapter
from common.observability import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the JustNews retrieval re-ranker. Given a search query and a set"
    ' of candidate passages, return JSON in the form {"scores": [{"id":'
    ' "candidate-id", "score": 0.0-1.0}, ...]}. Include every'
    " candidate exactly once, assign higher scores to more relevant passages,"
    " and keep explanations brief if included."
)


class CandidateLike(Protocol):
    id: str
    text: str


@dataclass(frozen=True)
class RankedCandidate:
    id: str
    score: float


class ReRankerMistralAdapter(BaseMistralJSONAdapter):
    """Adapter wrapper that converts query + passages into normalized scores."""

    def __init__(self) -> None:
        super().__init__(
            agent_name="re_ranker",
            adapter_name="mistral_re_ranker_v1",
            system_prompt=SYSTEM_PROMPT,
            disable_env="RE_RANKER_DISABLE_MISTRAL",
            defaults={
                "max_chars": 3000,
                "max_new_tokens": 256,
                "temperature": 0.1,
                "top_p": 0.85,
            },
        )

    def score_candidates(
        self, query: str, candidates: Sequence[CandidateLike]
    ) -> list[float] | None:
        if not self.enabled or not query.strip() or not candidates:
            return None

        prepared: list[tuple[str, str]] = []
        for cand in candidates:
            text = getattr(cand, "text", "") or ""
            cid = getattr(cand, "id", "")
            trimmed = self._truncate_content(text)
            if cid and trimmed:
                prepared.append((cid, trimmed))
        if not prepared:
            return None

        lines = ["Query:", query.strip(), "Candidates:"]
        for idx, (cid, snippet) in enumerate(prepared, start=1):
            lines.append(f"{idx}. id={cid}\n'''{snippet}'''")
        user_block = "\n".join(lines)
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_block},
        ]
        doc = self._chat_json(messages)
        if not doc:
            return None

        ranking = self._parse_scores(doc, [cid for cid, _ in prepared])
        if not ranking:
            return None
        return ranking

    def _parse_scores(
        self, payload: dict[str, object], candidate_order: list[str]
    ) -> list[float] | None:
        entries = None
        for key in ("scores", "rankings", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                entries = value
                break
        if entries is None and isinstance(payload.get("scores"), dict):
            entries = [
                {"id": cid, "score": payload["scores"].get(cid)}  # type: ignore[index]
                for cid in candidate_order
            ]

        scores: dict[str, float] = {}
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                cid = item.get("id") or item.get("candidate_id") or item.get("doc_id")
                if not cid:
                    continue
                try:
                    score_val = float(
                        item.get("score") or item.get("relevance") or item.get("weight")
                    )
                except (TypeError, ValueError):
                    continue
                scores[str(cid)] = max(0.0, min(score_val, 1.0))

        if not scores:
            return None

        ordered = [scores.get(cid, 0.0) for cid in candidate_order]
        return ordered
