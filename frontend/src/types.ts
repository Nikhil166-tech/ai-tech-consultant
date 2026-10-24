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
