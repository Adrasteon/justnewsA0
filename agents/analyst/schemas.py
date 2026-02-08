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
class PerArticleAnalysis:
    article_id: str | None = None
    language: str | None = "en"
    sentiment: dict[str, Any] | None = None
    bias: dict[str, Any] | None = None
    entities: list[dict[str, Any]] | None = None
    claims: list[Claim] | None = None
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
            "per_article": [p.to_dict() for p in (self.per_article or [])],
            "source_fact_checks": [
                sfc.to_dict() for sfc in (self.source_fact_checks or [])
            ],
            "cluster_fact_check_summary": self.cluster_fact_check_summary,
            "generated_at": self.generated_at,
        }
