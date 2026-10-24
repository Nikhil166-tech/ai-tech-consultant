export enum Intent {
  HOW_TO_CONFIGURE = "HOW_TO_CONFIGURE",
  FEATURE_INQUIRY = "FEATURE_INQUIRY",
  BILLING_ISSUE = "BILLING_ISSUE",
  ACCOUNT_ACCESS = "ACCOUNT_ACCESS",
  BUG_REPORT = "BUG_REPORT",
  CANCELLATION = "CANCELLATION",
  GENERAL_INQUIRY = "GENERAL_INQUIRY"
}

export enum RiskLevel {
  LOW = "LOW",
  MEDIUM = "MEDIUM",
  HIGH = "HIGH",
  CRITICAL = "CRITICAL"
}

export enum ProductArea {
  PAYMENTS_GATEWAYS = "PAYMENTS_GATEWAYS",
  MEMBERSHIP_PLANS = "MEMBERSHIP_PLANS",
  DOMAINS_DNS = "DOMAINS_DNS",
  EMAIL_TEMPLATES = "EMAIL_TEMPLATES",
  FORMS_RECAPTCHA = "FORMS_RECAPTCHA",
  SEARCH_LOCATIONS = "SEARCH_LOCATIONS",
  ANALYTICS_TRACKING = "ANALYTICS_TRACKING",
  MEMBER_EXPORT_IMPORT = "MEMBER_EXPORT_IMPORT",
  LISTINGS_MANAGEMENT = "LISTINGS_MANAGEMENT",
  ACCOUNT_SECURITY = "ACCOUNT_SECURITY",
  UNKNOWN = "UNKNOWN"
}

export interface KindTuple {
  intent: Intent;
  riskLevel: RiskLevel;
  productArea: ProductArea;
  key: string; // e.g. "HOW_TO_CONFIGURE:LOW:PAYMENTS_GATEWAYS"
}

export function formatKindKey(intent: Intent, riskLevel: RiskLevel, productArea: ProductArea): string {
  return `${intent}:${riskLevel}:${productArea}`;
}

export interface CustomerEmail {
  id: string;
  senderEmail: string;
  senderName?: string;
  subject: string;
  body: string;
  receivedAt: string;
}

export interface EmailClassification {
  kind: KindTuple;
  confidence: number;
  urgency: "LOW" | "NORMAL" | "HIGH";
  reasoning: string;
  requiresHumanReview: boolean;
  riskFlags: string[];
  parentSettingType: string;
  specificLabel: string;
  labelKey: string; // e.g. "Design Settings -> Header"
}

export interface Task1Citation {
  url: string;
  title: string;
  category: string;
  folder: string;
  section_heading: string;
  snippet: string;
  source_type: string;
  provenance_notes?: string | null;
}

export interface Task1AskResponse {
  answer: string;
  citations: Task1Citation[];
  evidence_score: number;
  evidence_status: "STRONG" | "PARTIAL" | "INSUFFICIENT" | "NONE";
  is_known: boolean;
  needs_human_review: boolean;
  expert_task_id?: string | null;
  visual_references: Array<{
    url: string;
    alt?: string;
    caption?: string;
    section_heading?: string;
    visual_status?: string;
  }>;
  confidence_score?: number;
}

export interface DraftReply {
  id: string;
  emailId: string;
  subject: string;
  body: string;
  generatedAt: string;
  promptVersion: "v1_baseline" | "v2_feedback_enhanced";
  knowledgeEvidenceScore: number;
  citations: Task1Citation[];
  autoSendEligible: boolean;
  blockReason?: string;
}

export type ReviewAction = "APPROVE" | "EDIT" | "REJECT";

export interface HumanReviewRecord {
  id: string;
  emailId: string;
  draftId: string;
  kindKey: string;
  parentSettingType?: string;
  specificLabel?: string;
  labelKey?: string;
  action: ReviewAction;
  originalDraft: string;
  finalSentReply?: string; // undefined if REJECT
  wasUnchanged: boolean;
  diffSummary?: string;
  reviewerId: string;
  reviewedAt: string;
  notes?: string;
}

export interface AutomaticDeliveryRecord {
  id: string;
  interactionId: string;
  emailId: string;
  draftId: string;
  kindKey: string;
  labelKey?: string;
  sentReply: string;
  sentAt: string;
  promptVersion: "v1_baseline" | "v2_feedback_enhanced";
  gmailMessageId?: string;
}

export type InteractionStatus = "PENDING_REVIEW" | "AUTO_SENT" | "APPROVED" | "EDITED" | "REJECTED";

export interface InteractionRecord {
  id: string; // matches draft.id or email.id
  email: CustomerEmail;
  classification: EmailClassification;
  task1Status: {
    success: boolean;
    isAvailable: boolean;
    evidenceScore: number;
    evidenceStatus: string;
    needsHumanReview: boolean;
    fallbackReason?: string;
  };
  draft: DraftReply;
  promptVersion: "v1_baseline" | "v2_feedback_enhanced";
  routingDecision: "AUTO_SENT" | "HUMAN_REVIEW_QUEUE";
  status: InteractionStatus;
  finalSentReply?: string;
  reviewAction?: ReviewAction;
  reviewerId?: string;
  reviewedAt?: string;
  reviewNotes?: string;
  gmailMessageId?: string;
  gmailThreadId?: string;
  createdAt: string;
  updatedAt: string;
}

export interface AutonomyState {
  kindKey: string;
  unchangedStreak: number;
  autonomyEnabled: boolean;
  totalDrafts: number;
  totalSentWithoutChanges: number;
  lastFailureReason?: string;
  lastRevokedReason?: string;
  revokedAt?: string;
  updatedAt: string;
}

export interface LabelAutonomyState {
  labelKey: string; // e.g. "Design Settings -> Header"
  parentSettingType: string;
  specificLabel: string;
  unchangedStreak: number;
  requiredThreshold: number; // Configurable threshold X, default 3
  autonomyEnabled: boolean;
  disabledByUser: boolean;
  totalDrafts: number;
  totalSentWithoutChanges: number;
  lastFailureReason?: string;
  updatedAt: string;
}

export interface AutonomyGlobalSettings {
  defaultThreshold: number;
  emergencyStop: boolean;
  requireGmailConnection: boolean;
  minEvidenceScore: number;
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

export interface GmailMessageRecord {
  id: string;
  threadId: string;
  snippet: string;
  subject: string;
  sender: string;
  recipient: string;
  bodyText: string;
  date: string;
  labels: string[];
  inReplyTo?: string;
  references?: string;
  processed?: boolean;
  interactionId?: string;
}

export interface AutonomyRevocationRequest {
  kindKey: string;
  reason: string;
  revokedBy?: string;
}

export interface ProcessingResult {
  email: CustomerEmail;
  classification: EmailClassification;
  knowledgeResponse?: Task1AskResponse;
  draft: DraftReply;
  routedTo: "AUTO_SENT" | "HUMAN_REVIEW_QUEUE";
  autonomyState: AutonomyState;
  labelAutonomyState?: LabelAutonomyState;
  interactionId: string;
  finalSentReply?: string;
  gmailMessageId?: string;
}
