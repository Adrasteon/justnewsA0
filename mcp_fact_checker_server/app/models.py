from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime

class EvidenceType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TABLE = "table"

class Evidence(BaseModel):
    content: str
    source_url: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.TEXT
    confidence: float = 0.0
    metadata: Dict[str, Any] = {}

class FactCheckRequest(BaseModel):
    fact: str = Field(..., description="The statement to verify")
    context: Optional[str] = Field(None, description="Context surrounding the fact")
    sources: Optional[List[str]] = Field(None, description="Specific sources to check")
    options: Dict[str, Any] = Field(default_factory=dict, description="Configuration options")

class FactCheckResult(BaseModel):
    fact: str
    is_accurate: bool
    verdict: str = Field(..., description="The final determination: 'proven', 'plausible', 'unverified', 'improbable', or 'disproven'")
    confidence: float
    evidence: List[Evidence]
    explanation: str
    trusted_sources: List[str] = []
    misleading_sources: List[str] = []
    model_trace: Dict[str, Any] = {}
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
    result: Optional[FactCheckResult] = None
    error: Optional[str] = None