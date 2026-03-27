from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TABLE = "table"


class Verdict(str, Enum):
    TRUE = "True"
    LIKELY_TRUE = "Likely True"
    UNCERTAIN = "Uncertain"
    LIKELY_FALSE = "Likely False"
    FALSE = "False"

class Evidence(BaseModel):
    content: str
    source_url: str | None = None
    evidence_type: EvidenceType = EvidenceType.TEXT
    confidence: float = 0.0
    metadata: dict[str, Any] = {}

class FactCheckRequest(BaseModel):
    fact: str = Field(..., description="The statement to verify")
    context: str | None = Field(None, description="Context surrounding the fact")
    sources: list[str] | None = Field(None, description="Specific sources to check")
    options: dict[str, Any] = Field(default_factory=dict, description="Configuration options")

class FactCheckResult(BaseModel):
    fact: str
    is_accurate: bool
    verdict: Verdict = Field(..., description="The final determination: 'True', 'Likely True', 'Uncertain', 'Likely False', or 'False'")
    confidence: float
    evidence: list[Evidence]
    explanation: str
    trusted_sources: list[str] = []
    misleading_sources: list[str] = []
    model_trace: dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobRecord(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    result: FactCheckResult | None = None
    error: str | None = None
