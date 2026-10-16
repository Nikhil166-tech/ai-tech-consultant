from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from enum import Enum

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class EvidenceStatus(str, Enum):
    STRONG = "STRONG"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    NONE = "NONE"

class ImageMetadata(BaseModel):
    url: str
    alt: Optional[str] = ""
    caption: Optional[str] = ""
    context_text: Optional[str] = ""
    section_heading: Optional[str] = ""

class Article(BaseModel):
    url: str
    title: str
    category: Optional[str] = "General"
    folder: Optional[str] = "General"
    body_text: str
    content_hash: Optional[str] = None
    images: List[ImageMetadata] = Field(default_factory=list)
    last_modified: Optional[str] = None
    etag: Optional[str] = None
    status: str = "active"  # 'active' or 'removed'
    crawled_at: datetime = Field(default_factory=utc_now)

class ArticleChunk(BaseModel):
    id: str
    article_url: str
    title: str
    category: str
    folder: str
    section_heading: str = "Overview"
    chunk_index: int
    text: str
    visual_context: Optional[str] = ""
    images: List[ImageMetadata] = Field(default_factory=list)
    embedding: Optional[List[float]] = None
    source_type: str = "OFFICIAL_DOC"  # 'OFFICIAL_DOC' or 'EXPERT_RESOLUTION'
    provenance_notes: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    category: Optional[str] = None

class SearchResult(BaseModel):
    article_url: str
    title: str
    category: str
    folder: str
    section_heading: str = "Overview"
    snippet: str
    score: float
    source_type: str = "OFFICIAL_DOC"
    provenance_notes: Optional[str] = None
    images: List[ImageMetadata] = Field(default_factory=list)

class AskRequest(BaseModel):
    question: str
    category_filter: Optional[str] = None
    history: List[Dict[str, str]] = Field(default_factory=list)

class Citation(BaseModel):
    url: str
    title: str
    category: str
    folder: str
    section_heading: str
    snippet: str
    source_type: str = "OFFICIAL_DOC"
    provenance_notes: Optional[str] = None

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    confidence_score: float  # Calibrated 0.0 to 1.0 (never artificially forced)
    evidence_status: EvidenceStatus
    is_known: bool
    needs_human_review: bool
    expert_task_id: Optional[str] = None
    visual_references: List[ImageMetadata] = Field(default_factory=list)

class ExpertTaskCreate(BaseModel):
    question: str
    context: Optional[str] = ""
    requester_email: Optional[str] = None

class ExpertTask(BaseModel):
    id: str
    question: str
    context: Optional[str] = ""
    requester_email: Optional[str] = None
    status: str = "pending"  # 'pending', 'resolved'
    expert_answer: Optional[str] = None
    created_at: str
    resolved_at: Optional[str] = None
    expert_id: Optional[str] = None
    version: Optional[str] = "1.0"
    provenance_notes: Optional[str] = None

class ExpertTaskResolve(BaseModel):
    expert_answer: str
    expert_id: Optional[str] = "expert_reviewer"
    version: Optional[str] = "1.0"
    provenance_notes: Optional[str] = "Manual product specialist review"

class SyncReport(BaseModel):
    total_in_sitemap: int
    added: int
    updated: int
    removed: int
    unchanged: int
    duration_seconds: float

class SyncStatus(BaseModel):
    status: Literal["idle", "running", "completed", "failed"]
    current_step: str
    pages_crawled: int = 0
    total_sitemap_urls: int = 0
    last_error: Optional[str] = None
    last_report: Optional[SyncReport] = None
    updated_at: str
