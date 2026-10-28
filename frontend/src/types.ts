export interface User {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export interface SitemapItem {
  id: string;
  url?: string;
  root_url?: string;
  name?: string;
  user_id?: string;
  last_validated_at?: string | null;
  status: string;
  discovered_sitemaps_count?: number;
  total_urls_count?: number;
  progress_percent?: number;
  current_run_status?: string;
  last_error?: string | null;
  refresh_interval?: string;
  refresh_interval_days?: number;
  next_refresh_at?: string | null;
  last_refresh_started_at?: string | null;
  last_refresh_completed_at?: string | null;
  schedule_status?: "active" | "paused" | "disabled" | string;
  created_at: string;
  updated_at?: string;
}

export interface SitemapPreview {
  submitted_url: string;
  discovered_sitemaps_count: number;
  nested_sitemaps_count: number;
  total_extracted_urls: number;
  total_unique_urls: number;
  first_url: string | null;
  last_url: string | null;
  first_url_lastmod: string | null;
  last_url_lastmod: string | null;
  validation_status: "VALID" | "INVALID";
  errors: string[];
}

export interface IndexingEstimate {
  observed_pages_per_5min: number;
  estimated_pages_per_hour: number;
  estimated_remaining_seconds: number;
  formatted_estimate: string;
  is_estimate_only: boolean;
  notes: string;
}

export interface RefreshRunSummary {
  id: string;
  sitemap_id: string;
  status: string;
  started_at: string;
  first_successful_fetch_at: string | null;
  last_successful_fetch_at: string | null;
  completed_at: string | null;
  total_discovered_urls: number;
  total_fetched_urls: number;
  added_count: number;
  updated_count: number;
  unchanged_count: number;
  failed_count: number;
  pending_count: number;
  quarantined_count: number;
}

export interface RefreshRunUrlItem {
  url: string;
  http_status: number | null;
  action_taken: string;
  content_changed: boolean;
  content_hash: string | null;
  sitemap_lastmod: string | null;
  fetched_at: string | null;
  error_message: string | null;
}

export interface QuarantineRecord {
  id: string;
  article_id: string;
  url: string;
  title: string;
  quarantine_reason: string;
  consecutive_failures: number;
  last_http_status: number | null;
  replacement_url: string | null;
  quarantined_at: string;
  restored_at: string | null;
}

export interface CustomerEmail {
  id: string;
  senderEmail: string;
  senderName?: string;
  subject: string;
  body: string;
  receivedAt?: string;
}

export interface InteractionRecord {
  id: string;
  email: CustomerEmail;
  classification: {
    parentSettingType: string;
    specificLabel: string;
    labelKey: string;
    urgency: "LOW" | "NORMAL" | "HIGH";
    reasoning: string;
    requiresHumanReview: boolean;
    riskFlags: string[];
    kind: {
      intent: string;
      riskLevel: string;
      productArea: string;
      key: string;
    };
  };
  draft: {
    id: string;
    subject: string;
    body: string;
    generatedAt: string;
    knowledgeEvidenceScore: number;
    autoSendEligible: boolean;
    blockReason?: string;
    citations: Array<{
      title: string;
      section_heading: string;
      url: string;
    }>;
  };
  routingDecision: "AUTO_SENT" | "HUMAN_REVIEW_QUEUE";
  folder?: "INBOX" | "DRAFTS" | "SENT" | "SPAM" | "TRASH";
  status: "PENDING_REVIEW" | "AUTO_SENT" | "APPROVED" | "EDITED" | "REJECTED";
  finalSentReply?: string;
  reviewAction?: "APPROVE" | "EDIT" | "REJECT";
  reviewerId?: string;
  gmailMessageId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface LabelAutonomyState {
  labelKey: string;
  parentSettingType: string;
  specificLabel: string;
  unchangedStreak: number;
  requiredThreshold: number;
  autonomyEnabled: boolean;
  disabledByUser: boolean;
  totalDrafts: number;
  totalSentWithoutChanges: number;
  lastFailureReason?: string;
  updatedAt: string;
}

export interface TaxonomyItem {
  id: string;
  parentSettingType: string;
  specificLabel: string;
  description: string;
  keywords: string[];
  synonyms: string[];
  enabled: boolean;
}

export interface GmailAccountStatus {
  isConnected: boolean;
  email?: string;
  name?: string;
  tokenExpiry?: string;
  lastSyncAt?: string;
  scopes?: string[];
  isMock?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Array<{
    title: string;
    section_heading: string;
    url: string;
  }>;
  evidence_status?: string;
  evidence_score?: number;
  timestamp: string;
}

export interface URLHealthStatus {
  url: string;
  canonical_url?: string;
  user_id?: string;
  sitemap_id?: string | null;
  consecutive_failure_count: number;
  configured_threshold: number;
  expected_action: string;
  pending_action?: string;
  action_rule?: string;
  redirect_destination_url?: string | null;
  last_checked_at: string;
  last_successful_fetch_at?: string | null;
  last_attempted_fetch_at?: string | null;
  last_http_status?: number | null;
  is_in_sitemap: boolean;
  is_healthy: boolean;
  failure_reason?: string | null;
  action_history?: Array<Record<string, any>>;
}

export interface ArchivedArticleItem {
  id: string;
  url: string;
  canonical_url?: string;
  sitemap_id?: string | null;
  user_id?: string;
  title: string;
  chunks_count: number;
  original_indexed_at?: string | null;
  archived_at: string;
  archive_reason: string;
  last_known_http_status?: number | null;
  replacement_url?: string | null;
  restore_eligible: boolean;
  retention_preset: string;
  retention_days: number;
  retention_expires_at?: string | null;
}

export interface ArchivedArticleDetail extends ArchivedArticleItem {
  content: string;
  chunks_preview: string[];
  last_successful_version?: string;
  audit_history: Array<Record<string, any>>;
}

export interface ArticleRedirectItem {
  id: string;
  source_url: string;
  destination_url: string;
  http_status: number;
  hop_count: number;
  redirect_chain: string[];
  detected_at: string;
  replacement_indexed: boolean;
  replacement_article_url?: string | null;
  notes?: string | null;
}

export interface ArticleHistoryItem {
  id: string;
  url: string;
  user_id: string;
  sitemap_id?: string | null;
  version: string;
  title: string;
  previous_title?: string | null;
  new_title?: string | null;
  change_type: string;
  change_classification?: string;
  previous_hash?: string | null;
  new_hash?: string | null;
  summary_diff?: string | null;
  content_snapshot?: string | null;
  extraction_version: string;
  embedding_model: string;
  embedding_version: string;
  refresh_run_id?: string | null;
  recorded_at: string;
}

export interface SchedulerStatus {
  is_running: boolean;
  total_scheduled_sitemaps: number;
  due_sitemaps_count: number;
  active_jobs_count: number;
  last_run_started_at?: string | null;
  server_time_utc: string;
}

export interface ModelRoleStatusItem {
  role: string;
  primary_model: string;
  fallback_models: string[];
  timeout_seconds: number;
  max_attempts: number;
  availability_status: "CONFIGURED" | "DEGRADED" | "UNAVAILABLE";
  provider: "google" | "anthropic" | "deterministic";
  temperature: number;
  supports_structured_output: boolean;
  last_successful_invocation?: string | null;
  estimated_cost_per_1k_tokens: number;
}

export interface AIModelStatusResponse {
  roles: ModelRoleStatusItem[];
  spending_limit_usd: number;
  current_estimated_spend_usd: number;
  system_status: string;
}

export type CapabilityStatus = "SUPPORTED" | "UNSUPPORTED" | "PARTIAL_NATIVE" | "NEEDS_CUSTOM_DEV" | "UNKNOWN";
export type RequirementLifecycleStatus = "NEW" | "CHANGED" | "UNCHANGED" | "REMOVED" | "OUT_OF_SCOPE";

export interface RequirementItem {
  id: string;
  title: string;
  description: string;
  source_quote?: string;
  source_speaker?: string;
  capability_status: CapabilityStatus;
  evidence_citations?: Array<{
    title: string;
    section_heading?: string;
    url: string;
    source_type?: string;
  }>;
  estimated_hours_native?: number;
  estimated_hours_custom?: number;
  technical_notes?: string;
  assumptions?: string[];
  open_questions?: string[];
  acceptance_criteria?: string[];
  lifecycle_status: RequirementLifecycleStatus;
  version: number;
}

export interface ScopeChangeSet {
  meeting_id: string;
  detected_at: string;
  added_requirements: string[];
  changed_requirements: string[];
  removed_requirements: string[];
  unchanged_requirements: string[];
  notes?: string;
}

export interface ProjectScope {
  project_id: string;
  version: number;
  client_ready: boolean;
  user_id?: string;
  created_at: string;
  updated_at: string;
  approved_by?: string;
  approved_at?: string;
  requirements: RequirementItem[];
  changesets: ScopeChangeSet[];
  proposal_markdown?: string;
}


