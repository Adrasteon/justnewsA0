from typing import Any

from pydantic import BaseModel


class NeuralAssessment(BaseModel):
    """Standardized payload produced by the Fact Checker agent for reasoning."""

    version: str = "1.0"
    confidence: float
    source_credibility: float | None = None
    extracted_claims: list[str] = []
    evidence_matches: list[dict[str, Any]] = []
    processing_metadata: dict[str, Any] = {}


class ReasoningInput(BaseModel):
    """Input wrapper for the reasoning pipeline containing a neural assessment and article metadata."""

    assessment: NeuralAssessment
    article_metadata: dict[str, Any] | None = {}


class PipelineResult(BaseModel):
    version: str = "1.0"
    overall_confidence: float
    verification_status: str
    explanation: Any
    neural_assessment: NeuralAssessment
    logical_validation: dict[str, Any]
    processing_summary: dict[str, Any]
