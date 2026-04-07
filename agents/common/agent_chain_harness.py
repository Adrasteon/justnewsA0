"""Lightweight harness that feeds normalized articles into core editorial adapters.

This helper is used by integration tests (and future CI harnesses) to
exercise the journalist, fact_checker, and synthesizer adapters in dry-run
mode using deterministic fixtures. It avoids spinning up the heavy FastAPI
agents while still covering the data contracts between stages.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from dataclasses import dataclass as _dataclass

from agents.journalist.model_adapter import JournalistModelAdapter
from agents.synthesizer.model_adapter import SynthesizerModelAdapter
from common.observability import get_logger

try:
    from agents.fact_checker.model_adapter import (
        ClaimAssessment,
        FactCheckerModelAdapter,
    )
except Exception:
    @_dataclass
    class ClaimAssessment:
        verdict: str
        confidence: float
        score: float
        rationale: str
        evidence_needed: bool = False

    class FactCheckerModelAdapter:
        """Container-runtime compatible fallback adapter.

        The fact-checker now runs as a separate service/container. For local harness
        usage we keep deterministic in-process fallback semantics to avoid hard
        network coupling during test collection.
        """

        def evaluate_claim(self, claim: str, context: str | None = None) -> ClaimAssessment | None:
            if not claim or not claim.strip():
                return None
            text = f"{claim} {context or ''}".lower()
            pos = sum(1 for token in ("official", "confirmed", "according to", "verified") if token in text)
            neg = sum(1 for token in ("alleged", "rumor", "unconfirmed", "fake") if token in text)
            score = max(0.0, min(1.0, 0.5 + (0.12 * pos) - (0.12 * neg)))
            verdict = "verified" if score >= 0.7 else ("refuted" if score <= 0.3 else "unclear")
            return ClaimAssessment(
                verdict=verdict,
                confidence=max(0.5, min(0.95, score)),
                score=score,
                rationale="Fallback compatibility assessment",
                evidence_needed=score < 0.7,
            )

logger = get_logger(__name__)


@dataclass
class NormalizedArticle:
    article_id: str
    url: str
    title: str
    text: str
    metadata: dict[str, Any] | None = None


@dataclass
class AgentChainResult:
    article_id: str
    story_brief: dict[str, Any] | None
    fact_checks: list[dict[str, Any]]
    draft: dict[str, Any] | None
    acceptance_score: float
    needs_followup: bool


class AgentChainHarness:
    """In-process harness that runs the core adapters for a normalized article."""

    def __init__(self) -> None:
        self.journalist_adapter = JournalistModelAdapter()
        self.fact_checker_adapter = FactCheckerModelAdapter()
        self.synthesizer_adapter = SynthesizerModelAdapter()

    def run_article(self, article: NormalizedArticle) -> AgentChainResult:
        story_brief = self._build_story_brief(article)
        fact_checks = self._run_fact_checks(article)
        draft = self._build_draft(article)

        verified = sum(1 for fc in fact_checks if fc.get("verdict") == "verified")
        acceptance_score = verified / max(len(fact_checks), 1) if fact_checks else 0.0
        needs_followup = acceptance_score < 0.6 or any(
            fc.get("verdict") == "refuted" for fc in fact_checks
        )

        return AgentChainResult(
            article_id=article.article_id,
            story_brief=story_brief,
            fact_checks=fact_checks,
            draft=draft,
            acceptance_score=round(acceptance_score, 3),
            needs_followup=needs_followup,
        )

    # Internal helpers -------------------------------------------------

    def _build_story_brief(self, article: NormalizedArticle) -> dict[str, Any] | None:
        fallback = {
            "headline": article.title,
            "summary": article.text[:240],
            "key_points": [],
        }
        try:
            brief = self.journalist_adapter.generate_story_brief(
                markdown=article.text,
                url=article.url,
                title=article.title,
            )
            return brief or fallback
        except AttributeError:
            logger.warning(
                "Journalist adapter missing generate_story_brief; falling back to infer()."
            )
            summary = self.journalist_adapter.infer(
                f"Summarize the following content in two sentences and list bullet points:\n{article.text[:2000]}"
            )
            fallback["summary"] = summary.get("text", "")
            return fallback

    def _run_fact_checks(self, article: NormalizedArticle) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        method = getattr(self.fact_checker_adapter, "evaluate_claim", None)
        claims = list(_extract_claims(article.text))
        if not method:
            logger.warning(
                "Fact-checker adapter missing evaluate_claim; skipping claim analysis."
            )
            return checks

        for claim in claims:
            try:
                assessment: ClaimAssessment | None = method(claim, article.text[:1200])
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Fact-checker adapter error: %s", exc)
                continue
            if assessment:
                checks.append(
                    {
                        "claim": claim,
                        "verdict": assessment.verdict,
                        "confidence": assessment.confidence,
                        "score": assessment.score,
                        "evidence_needed": assessment.evidence_needed,
                        "rationale": assessment.rationale,
                    }
                )
        return checks

    def _build_draft(self, article: NormalizedArticle) -> dict[str, Any] | None:
        snippets = [article.text]
        fallback = {
            "summary": article.text[:360],
            "key_points": [],
            "narrative_voice": "neutral",
            "cautions": [],
        }
        try:
            draft = self.synthesizer_adapter.summarize_cluster(
                snippets, context=article.title
            )
            if draft:
                return draft
            logger.warning(
                "Synthesizer adapter returned no draft; using fallback text."
            )
            return fallback
        except AttributeError:
            logger.warning(
                "Synthesizer adapter missing summarize_cluster; falling back to infer()."
            )
            completion = self.synthesizer_adapter.infer(
                f"Produce a neutral news draft for:\nTitle: {article.title}\nContent: {article.text[:2500]}"
            )
            fallback["summary"] = completion.get("text", fallback["summary"])
            return fallback


def _extract_claims(
    text: str, *, max_claims: int = 3, min_words: int = 8
) -> Iterable[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip()) if text else []
    claims: list[str] = []
    for sentence in sentences:
        if len(sentence.split()) < min_words:
            continue
        claims.append(sentence.strip())
        if len(claims) >= max_claims:
            break
    return claims
