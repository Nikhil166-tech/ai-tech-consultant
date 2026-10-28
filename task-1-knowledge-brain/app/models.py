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
    raw_content_hash: Optional[str] = None
    normalized_content_hash: Optional[str] = None
    images: List[ImageMetadata] = Field(default_factory=list)
    last_modified: Optional[str] = None
    etag: Optional[str] = None
    status: str = "active"  # 'active', 'quarantined', or 'removed'
    user_id: Optional[str] = "default_user"
    sitemap_id: Optional[str] = None
    extraction_version: Optional[str] = "2.0"
    embedding_model: Optional[str] = "BAAI/bge-small-en-v1.5"
    embedding_version: Optional[str] = "1.0"
    is_quarantined: Optional[bool] = False
    quarantine_reason: Optional[str] = None
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
    telemetry: Optional[Dict[str, Any]] = None

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
    canonical_root_url: Optional[str] = None
    url: Optional[str] = None
    name: str
    refresh_interval_days: int = 1
    refresh_interval: Optional[str] = None
    next_refresh_at: Optional[str] = None
    last_refresh_started_at: Optional[str] = None
    last_refresh_completed_at: Optional[str] = None
    schedule_status: str = "active"  # active, paused, disabled
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
    status: str = "running"  # queued, running, paused, interrupted, failed, completed
    stage: str = "QUEUED"    # QUEUED, FETCHING_SITEMAP, INDEXING_PAGES, COMPLETED
    progress_percent: float = 0.0
    lease_token: Optional[str] = None
    lease_expires_at: Optional[str] = None
    heartbeat_at: Optional[str] = None
    resumed_from_run_id: Optional[str] = None
    last_processed_url: Optional[str] = None
    error_details: Optional[str] = None
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
    REPLACED_BY_REDIRECT = "REPLACED_BY_REDIRECT"
    EXPLICIT_REMOVAL_410 = "EXPLICIT_REMOVAL_410"
    ADMIN_MANUAL = "ADMIN_MANUAL"
    LEGACY_EXTRACTION_DEFECT = "LEGACY_EXTRACTION_DEFECT"

class QuarantineRecord(BaseModel):
    id: str
    url: str
    sitemap_id: Optional[str] = None
    user_id: Optional[str] = "default_user"
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
    canonical_url: Optional[str] = None
    sitemap_id: Optional[str] = None
    user_id: str = "default_user"
    consecutive_failure_count: int = 0
    configured_threshold: int = 3
    expected_action: str = "Quarantine on 3 consecutive failures"
    pending_action: Optional[str] = None
    action_rule: str = "QUARANTINE_ON_CONSECUTIVE_FAILURES"
    last_checked_at: str
    last_http_status: Optional[int] = None
    last_successful_fetch_at: Optional[str] = None
    last_attempted_fetch_at: Optional[str] = None
    is_in_sitemap: bool = True
    is_healthy: bool = True
    failure_reason: Optional[str] = None
    redirect_destination_url: Optional[str] = None
    action_history: List[Dict[str, Any]] = Field(default_factory=list)

class UserSettings(BaseModel):
    user_id: str = "default_user"
    sitemap_refresh_interval_days: int = 1
    url_quarantine_threshold_x: int = 3
    url_quarantine_action: str = "QUARANTINE_ON_CONSECUTIVE_FAILURES"
    archive_retention_preset: str = "30_DAYS"  # 2_DAYS, 15_DAYS, 30_DAYS, CUSTOM
    archive_retention_days: int = 30
    email_approval_threshold_x: int = 3
    auto_send_enabled: bool = False
    emergency_disable: bool = False

    # Frontend-compatible alias fields
    url_verification_threshold: Optional[int] = None
    sitemap_refresh_frequency: Optional[str] = None
    quarantine_action_rule: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        if self.url_verification_threshold is not None:
            self.url_quarantine_threshold_x = self.url_verification_threshold
        else:
            self.url_verification_threshold = self.url_quarantine_threshold_x

        if self.quarantine_action_rule is not None:
            self.url_quarantine_action = self.quarantine_action_rule
        else:
            self.quarantine_action_rule = self.url_quarantine_action

        if self.sitemap_refresh_frequency is not None:
            mapping = {"daily": 1, "weekly": 7, "biweekly": 15, "monthly": 30}
            self.sitemap_refresh_interval_days = mapping.get(str(self.sitemap_refresh_frequency).lower(), self.sitemap_refresh_interval_days)
        else:
            self.sitemap_refresh_frequency = "daily" if self.sitemap_refresh_interval_days == 1 else f"{self.sitemap_refresh_interval_days} days"

# -------------------------------------------------------------
# Phase 7: Step 3 Production Scheduled Refresh & Archive Models
# -------------------------------------------------------------

class ScheduleUpdateRequest(BaseModel):
    refresh_interval_days: Optional[int] = None  # 1, 7, 15, 30
    schedule_status: Optional[str] = None       # active, paused, disabled

class SchedulerStatusResponse(BaseModel):
    status: str                                  # operational, degraded, paused
    enabled: bool
    active_workers_count: int = 0
    total_scheduled_sitemaps: int = 0
    due_sitemaps_count: int = 0
    next_due_at: Optional[str] = None
    last_scheduler_tick_at: Optional[str] = None
    fair_queue: List[Dict[str, Any]] = Field(default_factory=list)

class ArchivedArticleItem(BaseModel):
    id: str
    original_url: str
    canonical_url: str
    sitemap_id: Optional[str] = None
    user_id: str = "default_user"
    title: str
    snippet: str
    original_indexed_at: Optional[str] = None
    archived_at: str
    archive_reason: str
    historical_http_status: Optional[int] = None
    replacement_url: Optional[str] = None
    last_successful_version: str = "2.0"
    is_restore_eligible: bool = True
    retention_preset: str = "30_DAYS"           # 2_DAYS, 15_DAYS, 30_DAYS, CUSTOM
    retention_days: int = 30
    retention_expires_at: Optional[str] = None
    status: str = "archived"                    # archived, restored, review_pending, retention_expired
    audit_events_count: int = 0

class ArchivedArticleDetail(BaseModel):
    item: ArchivedArticleItem
    full_content: str
    chunks_count: int = 0
    audit_history: List[Dict[str, Any]] = Field(default_factory=list)

class ArchiveRetentionUpdateRequest(BaseModel):
    retention_preset: str                       # 2_DAYS, 15_DAYS, 30_DAYS, CUSTOM
    retention_days: Optional[int] = None

class ArticleRedirectItem(BaseModel):
    id: str
    source_url: str
    canonical_source_url: str
    target_url: str
    canonical_target_url: str
    sitemap_id: Optional[str] = None
    user_id: str = "default_user"
    http_status: int = 301
    hops_count: int = 1
    chain: List[str] = Field(default_factory=list)
    replacement_article_indexed: bool = True
    detected_at: str

class ArticleHistoryItem(BaseModel):
    id: str
    url: str
    version: str = "2.0"
    title: Optional[str] = None
    previous_title: Optional[str] = None
    new_title: Optional[str] = None
    change_type: str = "UPDATE"
    change_classification: str = "CONTENT_UPDATE"
    previous_hash: Optional[str] = None
    new_hash: Optional[str] = None
    previous_content_hash: Optional[str] = None
    new_content_hash: Optional[str] = None
    summary_diff: Optional[str] = None
    content_snapshot: Optional[str] = None
    recorded_at: str
    changed_at: Optional[str] = None
    refresh_run_id: Optional[str] = None

# -------------------------------------------------------------
# Phase 8: Step 4 AI Model Intelligence & Diagnostics Models
# -------------------------------------------------------------

class ModelRoleStatusItem(BaseModel):
    role: str
    primary_model: str
    fallback_models: List[str] = Field(default_factory=list)
    timeout_seconds: float = 15.0
    max_attempts: int = 3
    availability_status: str = "CONFIGURED"  # CONFIGURED | DEGRADED | UNAVAILABLE
    provider: str = "google"
    temperature: float = 0.2
    supports_structured_output: bool = True
    last_successful_invocation: Optional[str] = None
    estimated_cost_per_1k_tokens: float = 0.0001


class AIModelStatusResponse(BaseModel):
    roles: List[ModelRoleStatusItem] = Field(default_factory=list)
    spending_limit_usd: float = 50.0
    current_estimated_spend_usd: float = 0.0
    system_status: str = "OPERATIONAL"


