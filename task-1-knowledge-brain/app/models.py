from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, model_validator
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
    visual_verified: bool = False
    visual_status: str = "unavailable"  # 'verified', 'unverified', or 'unavailable'

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
    evidence_score: float = Field(
        ...,
        description="Heuristic evidence score (0.0 to 1.0) derived from hybrid retrieval and query term coverage. Not statistically calibrated against held-out validation data."
    )
    evidence_status: EvidenceStatus
    is_known: bool
    needs_human_review: bool
    expert_task_id: Optional[str] = None
    visual_references: List[ImageMetadata] = Field(default_factory=list)
    confidence_score: Optional[float] = None  # Deprecated alias for evidence_score

    @model_validator(mode="after")
    def populate_confidence_alias(self):
        if self.confidence_score is None:
            self.confidence_score = self.evidence_score
        return self

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

# -------------------------------------------------------------
# Phase 2: Custom Sitemap Management & Preview Models
# -------------------------------------------------------------

class SitemapCreate(BaseModel):
    url: str
    name: Optional[str] = None
    refresh_interval_days: Optional[int] = 1  # 1, 7, 15, 30
    refresh_interval: Optional[str] = None

class SitemapItem(BaseModel):
    id: str
    user_id: str = "default_user"
    root_url: str
    url: Optional[str] = None
    name: str
    refresh_interval_days: int = 1
    refresh_interval: Optional[str] = None
    status: str = "registered"  # registered, previewed, confirmed, indexing, active, failed
    discovered_sitemaps_count: int = 1
    total_urls_count: int = 0
    progress_percent: Optional[float] = None
    current_run_status: Optional[str] = None
    last_validated_at: Optional[str] = None
    last_preview_json: Optional[str] = None
    last_confirmed_at: Optional[str] = None
    created_at: str
    updated_at: str

class SitemapPreview(BaseModel):
    submitted_url: str
    discovered_sitemaps_count: int
    nested_sitemaps_count: int
    total_extracted_urls: int
    total_unique_urls: int
    first_url: Optional[str] = None
    first_url_lastmod: Optional[str] = None
    last_url: Optional[str] = None
    last_url_lastmod: Optional[str] = None
    validation_status: str  # 'valid', 'invalid', 'warning'
    validation_errors: List[str] = Field(default_factory=list)
    sample_urls: List[Dict[str, Any]] = Field(default_factory=list)
    can_index: bool = False

class IndexingEstimate(BaseModel):
    pages_processed_5min: int = 0
    crawl_duration_avg_sec: float = 0.0
    chunk_duration_avg_sec: float = 0.0
    embed_duration_avg_sec: float = 0.0
    db_duration_avg_sec: float = 0.0
    observed_throughput_pages_per_min: float = 0.0
    total_pages_remaining: int = 0
    estimated_remaining_seconds: float = 0.0
    estimated_completion_time_human: str = "Calculating..."
    disclaimer: str = "Estimate based on current 5-minute rolling throughput; not a guaranteed SLA"
    is_interrupted: bool = False
    checkpoint_url: Optional[str] = None

# -------------------------------------------------------------
# Phase 3: Scheduled Refresh Runs Models
# -------------------------------------------------------------

class RefreshRunSummary(BaseModel):
    id: str
    sitemap_id: str
    user_id: str = "default_user"
    started_at: str
    first_successful_fetch_at: Optional[str] = None
    last_successful_fetch_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_discovered_urls: int = 0
    total_successfully_fetched_urls: int = 0
    added_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    quarantined_count: int = 0
    status: str = "running"  # running, completed, failed, interrupted
    progress_percent: float = 0.0
    estimate: Optional[IndexingEstimate] = None

class RefreshRunUrlItem(BaseModel):
    url: str
    status: str  # NEW, CHANGED, UNCHANGED, FAILED, PENDING, QUARANTINED, REDIRECT_301
    http_status: Optional[int] = None
    lastmod: Optional[str] = None
    fetched_at: Optional[str] = None
    error_message: Optional[str] = None

class RefreshRunDetail(BaseModel):
    summary: RefreshRunSummary
    urls: List[RefreshRunUrlItem] = Field(default_factory=list)
    total_url_count: int = 0

# -------------------------------------------------------------
# Phase 4: URL Health and Quarantine Models
# -------------------------------------------------------------

class QuarantineReason(str, Enum):
    MISSING_404 = "MISSING_404"
    PERMANENT_REDIRECT_301 = "PERMANENT_REDIRECT_301"
    EXPLICIT_REMOVAL_410 = "EXPLICIT_REMOVAL_410"
    ADMIN_MANUAL = "ADMIN_MANUAL"

class QuarantineRecord(BaseModel):
    id: str
    url: str
    sitemap_id: Optional[str] = None
    title: str
    content: str
    chunks_count: int = 0
    last_known_http_status: int
    quarantine_reason: QuarantineReason
    replacement_url: Optional[str] = None
    detected_at: str
    quarantined_at: str
    restored_at: Optional[str] = None
    sitemap_presence_history: List[str] = Field(default_factory=list)

class URLHealthStatus(BaseModel):
    url: str
    sitemap_id: Optional[str] = None
    consecutive_failure_count: int = 0
    configured_threshold: int = 3
    expected_action: str = "Quarantine on 3 consecutive failures"
    last_checked_at: str
    last_http_status: Optional[int] = None
    is_in_sitemap: bool = True
    failure_reason: Optional[str] = None

class UserSettings(BaseModel):
    user_id: str = "default_user"
    sitemap_refresh_interval_days: int = 1
    url_quarantine_threshold_x: int = 3
    url_quarantine_action: str = "QUARANTINE_ON_CONSECUTIVE_FAILURES"
    email_approval_threshold_x: int = 3
    auto_send_enabled: bool = False
    emergency_disable: bool = False

