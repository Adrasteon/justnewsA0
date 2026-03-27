"""
Analyst Schemas - Output datatypes for Analyst agent

Defines minimal dataclasses used for AnalysisReport and Claim objects.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class ClaimVerdict:
    """Verdict for a single claim from fact-checker."""

    claim_text: str
    verdict: str  # 'verified', 'questionable', 'false', 'unverifiable'
    confidence: float
    evidence: list[dict[str, Any]] | None = None
    timestamp: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confidence"] = float(d["confidence"])
        return d


@dataclass
class SourceFactCheck:
    """Per-article fact-check result."""

    article_id: str
    fact_check_status: str  # 'passed', 'failed', 'needs_review', 'pending'
    overall_score: float
    claim_verdicts: list[ClaimVerdict] | None = field(default_factory=list)
    credibility_score: float | None = None
    source_url: str | None = None
    processed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    fact_check_trace: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "fact_check_status": self.fact_check_status,
            "overall_score": float(self.overall_score),
            "claim_verdicts": [cv.to_dict() for cv in (self.claim_verdicts or [])],
            "credibility_score": float(self.credibility_score)
            if self.credibility_score
            else None,
            "source_url": self.source_url,
            "processed_at": self.processed_at,
            "fact_check_trace": self.fact_check_trace,
        }


@dataclass
class Claim:
    claim_text: str
    start: int | None = None
    end: int | None = None
    confidence: float = 0.5
    claim_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confidence"] = float(d["confidence"])
        return d


@dataclass
class AttributionSpan:
    start: int | None = None
    end: int | None = None
    evidence_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AttributedStatement:
    statement_text: str
    speaker_entity_id: int | None = None
    speaker_name: str | None = None
    attribution_text: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    perspective_label: str | None = None
    is_opinion: bool = False
    counts_as_factual_corroboration: bool = True
    confidence: float = 0.5
    span: AttributionSpan | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement_text": self.statement_text,
            "speaker_entity_id": self.speaker_entity_id,
            "speaker_name": self.speaker_name,
            "attribution_text": self.attribution_text,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "perspective_label": self.perspective_label,
            "is_opinion": self.is_opinion,
            "counts_as_factual_corroboration": self.counts_as_factual_corroboration,
            "confidence": float(self.confidence),
            "span": self.span.to_dict() if self.span else None,
            "metadata": self.metadata or {},
        }


@dataclass
class AttributedQuote:
    quote_text: str
    speaker_entity_id: int | None = None
    speaker_name: str | None = None
    attribution_text: str | None = None
    source_url: str | None = None
    source_domain: str | None = None
    perspective_label: str | None = None
    is_opinion: bool = False
    counts_as_factual_corroboration: bool = True
    confidence: float = 0.5
    span: AttributionSpan | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote_text": self.quote_text,
            "speaker_entity_id": self.speaker_entity_id,
            "speaker_name": self.speaker_name,
            "attribution_text": self.attribution_text,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "perspective_label": self.perspective_label,
            "is_opinion": self.is_opinion,
            "counts_as_factual_corroboration": self.counts_as_factual_corroboration,
            "confidence": float(self.confidence),
            "span": self.span.to_dict() if self.span else None,
            "metadata": self.metadata or {},
        }


@dataclass
class BalanceAssessment:
    disputed_topic: bool = False
    min_distinct_sides: int = 2
    distinct_sides_found: int = 0
    policy_result: str = "warning"
    missing_perspectives: list[str] | None = None
    opinion_items_count: int = 0
    corroborating_items_count: int = 0
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "disputed_topic": self.disputed_topic,
            "min_distinct_sides": int(self.min_distinct_sides),
            "distinct_sides_found": int(self.distinct_sides_found),
            "policy_result": self.policy_result,
            "missing_perspectives": self.missing_perspectives or [],
            "opinion_items_count": int(self.opinion_items_count),
            "corroborating_items_count": int(self.corroborating_items_count),
            "details": self.details or {},
        }


@dataclass
class PerArticleAnalysis:
    article_id: str | None = None
    language: str | None = "en"
    sentiment: dict[str, Any] | None = None
    bias: dict[str, Any] | None = None
    entities: list[dict[str, Any]] | None = None
    claims: list[Claim] | None = None
    statements: list[AttributedStatement] | None = None
    quotes: list[AttributedQuote] | None = None
    attribution_coverage: dict[str, Any] | None = None
    source_fact_check: SourceFactCheck | None = None
    processing_time_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "article_id": self.article_id,
            "language": self.language,
            "sentiment": self.sentiment,
            "bias": self.bias,
            "entities": self.entities,
            "claims": [c.to_dict() for c in self.claims or []],
            "statements": [s.to_dict() for s in self.statements or []],
            "quotes": [q.to_dict() for q in self.quotes or []],
            "attribution_coverage": self.attribution_coverage,
            "source_fact_check": self.source_fact_check.to_dict()
            if self.source_fact_check
            else None,
            "processing_time_seconds": self.processing_time_seconds,
        }


@dataclass
class AnalysisReport:
    cluster_id: str | None = None
    language: str | None = "en"
    articles_count: int = 0
    aggregate_sentiment: dict[str, Any] | None = None
    aggregate_bias: dict[str, Any] | None = None
    entities: list[dict[str, Any]] | None = None
    primary_claims: list[Claim] | None = None
    attributed_statements: list[AttributedStatement] | None = None
    attributed_quotes: list[AttributedQuote] | None = None
    balance_assessment: BalanceAssessment | None = None
    attribution_summary: dict[str, Any] | None = None
    per_article: list[PerArticleAnalysis] | None = None
    source_fact_checks: list[SourceFactCheck] | None = field(default_factory=list)
    cluster_fact_check_summary: dict[str, Any] | None = None
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "language": self.language,
            "articles_count": self.articles_count,
            "aggregate_sentiment": self.aggregate_sentiment,
            "aggregate_bias": self.aggregate_bias,
            "entities": self.entities or [],
            "primary_claims": [c.to_dict() for c in (self.primary_claims or [])],
            "attributed_statements": [
                s.to_dict() for s in (self.attributed_statements or [])
            ],
            "attributed_quotes": [q.to_dict() for q in (self.attributed_quotes or [])],
            "balance_assessment": self.balance_assessment.to_dict()
            if self.balance_assessment
            else None,
            "attribution_summary": self.attribution_summary,
            "per_article": [p.to_dict() for p in (self.per_article or [])],
            "source_fact_checks": [
                sfc.to_dict() for sfc in (self.source_fact_checks or [])
            ],
            "cluster_fact_check_summary": self.cluster_fact_check_summary,
            "generated_at": self.generated_at,
        }
