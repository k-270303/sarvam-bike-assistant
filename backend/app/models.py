from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


@dataclass
class ManualPage:
    document_name: str
    page_number: int
    text: str


@dataclass
class Chunk:
    chunk_id: str
    document_name: str
    page_start: int
    page_end: int
    section_title: str
    text: str


@dataclass
class SearchHit:
    chunk: Chunk
    lexical_score: float
    semantic_score: float
    combined_score: float


@dataclass
class ManualUploadState:
    upload_id: str
    filename: str
    total_chunks: int
    total_size: int
    chunks: dict[int, bytes] = field(default_factory=dict)


@dataclass
class SessionCorpus:
    session_id: str
    created_at: datetime
    updated_at: datetime
    documents: list[str] = field(default_factory=list)
    pages: list[ManualPage] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    lexical_index: object | None = None
    embedding_index: object | None = None
    pending_uploads: dict[str, ManualUploadState] = field(default_factory=dict)


class Citation(BaseModel):
    document_name: str
    page_start: int
    page_end: int
    section_title: str
    excerpt: str


class TroubleshootRequest(BaseModel):
    session_id: str
    query: str = Field(min_length=1)


class VisionObservation(BaseModel):
    visible_observations: list[str] = Field(default_factory=list)
    visible_text: list[str] = Field(default_factory=list)
    visible_components: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class QueryAnalysis(BaseModel):
    symptom: str
    component: Optional[str] = None
    urgency: Literal["low", "medium", "high"] = "low"
    ambiguity_level: float = Field(ge=0.0, le=1.0)
    clarification_needed: bool
    clarification_questions: list[str] = Field(default_factory=list)


class TroubleshootResponse(BaseModel):
    status: Literal["success", "clarification_needed", "low_confidence"]
    issue_summary: Optional[str] = None
    possible_cause: Optional[str] = None
    recommended_action: Optional[str] = None
    confidence_score: float
    confidence_level: Literal["high", "medium", "low"]
    citations: list[Citation] = Field(default_factory=list)
    safety_warning: Optional[str] = None
    escalation_recommendation: Optional[str] = None
    clarification_questions: list[str] = Field(default_factory=list)
    message: Optional[str] = None


class ChunkedUploadStartRequest(BaseModel):
    filename: str = Field(min_length=1)
    total_chunks: int = Field(ge=1, le=300)
    total_size: int = Field(gt=0)


class ChunkedUploadStartResponse(BaseModel):
    upload_id: str
    chunk_size_hint: int


class IngestResponse(BaseModel):
    session_id: str
    documents: list[str]
    pages_processed: int
    chunks_indexed: int
    warnings: list[str] = Field(default_factory=list)


class EvaluationCase(BaseModel):
    id: str
    query: str
    expected_terms: list[str] = Field(default_factory=list)
    expected_any_terms: list[str] = Field(default_factory=list)
    expected_document_names: list[str] = Field(default_factory=list)
    expected_status: Literal["success", "clarification_needed", "low_confidence"]
    category: Literal[
        "supported_exact",
        "supported_paraphrase",
        "ambiguous",
        "unsupported",
        "safety",
    ] = "supported_exact"
