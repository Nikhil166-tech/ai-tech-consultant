from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class ImageMetadata(BaseModel):
    url: str
    alt: Optional[str] = ""
    caption: Optional[str] = ""
    context_text: Optional[str] = ""

class Article(BaseModel):
    url: str
    title: str
    category: Optional[str] = "General"
    folder: Optional[str] = "General"
    body_text: str
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
    chunk_index: int
    text: str
    visual_context: Optional[str] = ""
    embedding: Optional[List[float]] = None

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    category: Optional[str] = None

class SearchResult(BaseModel):
    article_url: str
    title: str
    category: str
    folder: str
    snippet: str
    score: float
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
    snippet: str

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    confidence_score: float  # 0.0 to 1.0
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

class ExpertTaskResolve(BaseModel):
    expert_answer: str

class SyncReport(BaseModel):
    total_in_sitemap: int
    added: int
    updated: int
    removed: int
    unchanged: int
    duration_seconds: float
