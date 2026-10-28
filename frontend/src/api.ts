import {
  User,
  SitemapItem,
  SitemapPreview,
  IndexingEstimate,
  RefreshRunSummary,
  RefreshRunUrlItem,
  QuarantineRecord,
  InteractionRecord,
  LabelAutonomyState,
  TaxonomyItem,
  GmailAccountStatus,
  CustomerEmail,
  AIModelStatusResponse,
  ProjectScope,
  ScopeChangeSet
} from "./types";

function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|;\\s*)csrf_token=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {})
  };

  // Attach CSRF protection header for state-changing requests
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken && !headers["X-CSRF-Token"]) {
      headers["X-CSRF-Token"] = csrfToken;
    }
  }

  const res = await fetch(url, {
    ...options,
    headers,
    credentials: "include"
  });

  if (!res.ok) {
    let errorMsg = `Request failed (${res.status})`;
    try {
      const errData = await res.json();
      errorMsg = errData.detail || errData.error || errData.message || errorMsg;
    } catch {
      // ignore
    }

    // Auto-dispatch event on session expiration or unauthenticated access (excluding initial /me check)
    if (res.status === 401 && !url.includes("/api/v1/auth/me") && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("auth:unauthorized", { detail: { url, status: 401 } }));
    }

    throw new Error(errorMsg);
  }

  return res.json();
}

export const api = {
  // Auth
  getCurrentUser: () => fetchJson<{ user: User | null }>("/api/v1/auth/me"),
  login: (email: string, password: string) =>
    fetchJson<{ user: User }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  register: (email: string, password: string) =>
    fetchJson<{ user: User }>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password })
    }),
  demoLogin: () => fetchJson<{ user: User }>("/api/v1/auth/demo-login", { method: "POST" }),
  logout: () => fetchJson<{ success: boolean }>("/api/v1/auth/logout", { method: "POST" }),

  // Sitemaps
  listSitemaps: () => fetchJson<SitemapItem[]>("/api/v1/sitemaps"),
  previewSitemap: (url: string) =>
    fetchJson<SitemapPreview>("/api/v1/sitemaps/preview", {
      method: "POST",
      body: JSON.stringify({ url })
    }),
  createSitemap: (url: string, refresh_interval: string = "daily") =>
    fetchJson<SitemapItem>("/api/v1/sitemaps", {
      method: "POST",
      body: JSON.stringify({ url, refresh_interval })
    }),
  confirmIndexSitemap: (sitemap_id: string) =>
    fetchJson<RefreshRunSummary>(`/api/v1/sitemaps/${sitemap_id}/confirm-index`, {
      method: "POST"
    }),
  getIndexingEstimate: () => fetchJson<IndexingEstimate>("/api/v1/sitemaps/estimate"),
  updateSitemapSchedule: (sitemap_id: string, interval_days?: number, status?: string) =>
    fetchJson<SitemapItem>(`/api/v1/sitemaps/${sitemap_id}/schedule`, {
      method: "PUT",
      body: JSON.stringify({ refresh_interval_days: interval_days, schedule_status: status })
    }),
  getSchedulerStatus: () => fetchJson<SchedulerStatus>("/api/v1/scheduler/status"),
  triggerRefreshNow: (sitemap_id: string, force: boolean = false) =>
    fetchJson<RefreshRunSummary>(`/api/v1/sitemaps/${sitemap_id}/refresh-now?force=${force}`, {
      method: "POST"
    }),

  // Refresh Runs
  listRefreshRuns: (sitemap_id?: string) =>
    fetchJson<RefreshRunSummary[]>(`/api/v1/refresh-runs${sitemap_id ? `?sitemap_id=${sitemap_id}` : ""}`),
  getRefreshRunDetail: (run_id: string, search?: string, status?: string, limit: number = 200, offset: number = 0) => {
    const params = new URLSearchParams();
    if (search) params.append("search", search);
    if (status) params.append("status", status);
    params.append("limit", limit.toString());
    params.append("offset", offset.toString());
    return fetchJson<{ summary: RefreshRunSummary; urls: RefreshRunUrlItem[] }>(`/api/v1/refresh-runs/${run_id}?${params.toString()}`);
  },
  triggerRefreshRun: (sitemap_id: string) =>
    fetchJson<RefreshRunSummary>(`/api/v1/sitemaps/${sitemap_id}/trigger-refresh`, {
      method: "POST"
    }),

  // URL Health & Actions
  listHealthObservations: (params?: { status?: string; search?: string; limit?: number; offset?: number; sitemap_id?: string }) => {
    const query = new URLSearchParams();
    if (params?.status) query.append("status", params.status);
    if (params?.search) query.append("search", params.search);
    if (params?.limit) query.append("limit", params.limit.toString());
    if (params?.offset) query.append("offset", params.offset.toString());
    if (params?.sitemap_id) query.append("sitemap_id", params.sitemap_id);
    return fetchJson<URLHealthStatus[]>(`/api/v1/health-observations?${query.toString()}`);
  },
  cancelPendingHealthAction: (url: string) =>
    fetchJson<any>("/api/v1/health-observations/cancel-pending", {
      method: "POST",
      body: JSON.stringify({ url })
    }),
  reverifyUrl: (url: string) =>
    fetchJson<URLHealthStatus>(`/api/v1/health-observations/${encodeURIComponent(url)}/reverify`, {
      method: "POST"
    }),

  // Quarantine & Archive
  listQuarantinedArticles: () => fetchJson<QuarantineRecord[]>("/api/v1/quarantine"),
  restoreQuarantinedArticle: (article_id: string) =>
    fetchJson<{ success: boolean; article_id: string }>(`/api/v1/quarantine/${article_id}/restore`, {
      method: "POST"
    }),
  listArchivedArticles: (params?: { search?: string; reason?: string; limit?: number; offset?: number }) => {
    const query = new URLSearchParams();
    if (params?.search) query.append("search", params.search);
    if (params?.reason) query.append("reason", params.reason);
    if (params?.limit) query.append("limit", params.limit.toString());
    if (params?.offset) query.append("offset", params.offset.toString());
    return fetchJson<ArchivedArticleItem[]>(`/api/v1/archive?${query.toString()}`);
  },
  getArchivedArticleDetail: (id: string) => fetchJson<ArchivedArticleDetail>(`/api/v1/archive/${id}`),
  restoreArchivedArticle: (id: string) =>
    fetchJson<{ status: string; message: string }>(`/api/v1/archive/${id}/restore`, {
      method: "POST"
    }),
  updateArchiveRetention: (id: string, preset: string, days?: number) =>
    fetchJson<any>(`/api/v1/archive/${id}/retention`, {
      method: "PUT",
      body: JSON.stringify({ retention_preset: preset, retention_days: days })
    }),

  // Redirects & History
  listRedirects: () => fetchJson<ArticleRedirectItem[]>("/api/v1/redirects"),
  getArticleHistory: (url: string) => fetchJson<ArticleHistoryItem[]>(`/api/v1/articles/${encodeURIComponent(url)}/history`),
  getArticleHistoryDiff: (v1: string, v2: string) => fetchJson<any>(`/api/v1/article-history/diff?v1=${v1}&v2=${v2}`),

  // Settings
  getUserSettings: () => fetchJson<any>("/api/v1/settings"),
  updateUserSettings: (settings: any) =>
    fetchJson<any>("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify(settings)
    }),

  // Knowledge & AI Chat
  listArticles: (limit: number = 50) => fetchJson<any[]>(`/api/v1/articles?limit=${limit}`),
  askQuestion: (question: string, history: Array<{ role: string; content: string }> = []) =>
    fetchJson<{
      answer: string;
      citations: Array<{ title: string; section_heading: string; url: string }>;
      evidence_score: number;
      evidence_status: string;
      is_known: boolean;
      needs_human_review: boolean;
    }>("/api/v1/ask", {
      method: "POST",
      body: JSON.stringify({ question, history })
    }),

  // Inbox & Interactions
  listInteractions: () => fetchJson<InteractionRecord[]>("/api/v1/inbox/interactions"),
  getPendingReviews: () => fetchJson<{ count: number; pending: InteractionRecord[] }>("/api/v1/inbox/pending"),
  processEmail: (email: CustomerEmail, version: "v1" | "v2" = "v2") =>
    fetchJson<any>(`/api/v1/emails/process?version=${version}`, {
      method: "POST",
      body: JSON.stringify(email)
    }),
  submitReview: (
    interactionId: string,
    action: "APPROVE" | "EDIT" | "REJECT",
    reviewerId: string = "specialist_ui",
    finalReply?: string,
    notes?: string,
    sendViaGmail: boolean = false
  ) =>
    fetchJson<{ interaction: InteractionRecord; reviewRecord: any }>("/api/v1/inbox/review", {
      method: "POST",
      body: JSON.stringify({ interactionId, action, reviewerId, finalReply, notes, sendViaGmail })
    }),
  sendApprovedEmailViaGmail: (interactionId: string) =>
    fetchJson<{ success: boolean; messageId: string; threadId: string }>(
      `/api/v1/emails/${interactionId}/send-gmail`,
      { method: "POST" }
    ),

  // Autonomy
  getAutonomySettings: () => fetchJson<any>("/api/v1/autonomy/settings"),
  updateAutonomySettings: (settings: any) =>
    fetchJson<any>("/api/v1/autonomy/settings", {
      method: "PUT",
      body: JSON.stringify(settings)
    }),
  getLabelAutonomyStates: () => fetchJson<{ count: number; labels: LabelAutonomyState[] }>("/api/v1/autonomy/labels"),
  setLabelThreshold: (labelKey: string, threshold: number) =>
    fetchJson<LabelAutonomyState>("/api/v1/autonomy/labels/threshold", {
      method: "PUT",
      body: JSON.stringify({ labelKey, threshold })
    }),
  toggleLabelAutonomy: (labelKey: string, disabled: boolean) =>
    fetchJson<LabelAutonomyState>("/api/v1/autonomy/labels/toggle", {
      method: "PUT",
      body: JSON.stringify({ labelKey, disabled })
    }),
  toggleEmergencyStop: (enabled: boolean) =>
    fetchJson<{ emergencyStop: boolean; message: string }>("/api/v1/autonomy/emergency-stop", {
      method: "POST",
      body: JSON.stringify({ enabled })
    }),

  // Taxonomy
  getTaxonomy: () => fetchJson<TaxonomyItem[]>("/api/v1/taxonomy"),
  updateTaxonomy: (taxonomy: TaxonomyItem[]) =>
    fetchJson<{ success: boolean; taxonomy: TaxonomyItem[] }>("/api/v1/taxonomy", {
      method: "PUT",
      body: JSON.stringify(taxonomy)
    }),

  // Gmail
  getGmailStatus: () => fetchJson<GmailAccountStatus>("/api/v1/gmail/status"),
  getGmailAuthUrl: () => fetchJson<{ url: string }>("/api/v1/gmail/auth-url"),
  disconnectGmail: () => fetchJson<{ success: boolean }>("/api/v1/gmail/disconnect", { method: "POST" }),
  syncGmail: (maxCount: number = 20) =>
    fetchJson<{ fetched: number; processed: number; items: any[] }>("/api/v1/gmail/sync", {
      method: "POST",
      body: JSON.stringify({ maxCount })
    }),
  connectMockGmail: (email?: string, name?: string) =>
    fetchJson<{ success: boolean; status: GmailAccountStatus }>("/api/v1/gmail/mock-connect", {
      method: "POST",
      body: JSON.stringify({ email, name })
    }),

  // Feedback
  getFeedbackMetrics: (key?: string) =>
    fetchJson<any>(`/api/v1/feedback/metrics${key ? `?key=${encodeURIComponent(key)}` : ""}`),
  getFeedbackHistory: (key?: string) =>
    fetchJson<any[]>(`/api/v1/feedback/history${key ? `?key=${encodeURIComponent(key)}` : ""}`),

  // Gemini Model & API Key
  getGeminiSettings: () =>
    fetchJson<{ apiKeyConfigured: boolean; model: string; maskedKey: string }>("/api/v1/settings/gemini"),
  saveGeminiSettings: (apiKey: string, model: string = "gemini-3.5-flash") =>
    fetchJson<{ success: boolean; verified: boolean; message: string; model: string; maskedKey: string }>(
      "/api/v1/settings/gemini",
      {
        method: "POST",
        body: JSON.stringify({ apiKey, model })
      }
    ),

  // Step 4: AI Model Routing & Diagnostics
  getAIModelStatus: () => fetchJson<AIModelStatusResponse>("/api/v1/ai/models/status"),

  // Inbox Folder Actions & Real Compose
  moveToTrash: (id: string) =>
    fetchJson<{ success: boolean; folder: string; interaction: InteractionRecord }>(`/api/v1/inbox/${id}/trash`, {
      method: "POST"
    }),
  restoreFromTrash: (id: string) =>
    fetchJson<{ success: boolean; folder: string; interaction: InteractionRecord }>(`/api/v1/inbox/${id}/restore`, {
      method: "POST"
    }),
  toggleSpam: (id: string) =>
    fetchJson<{ success: boolean; folder: string; interaction: InteractionRecord }>(`/api/v1/inbox/${id}/spam`, {
      method: "POST"
    }),
  deleteForever: (id: string) =>
    fetchJson<{ success: boolean; message: string }>(`/api/v1/inbox/${id}/forever`, {
      method: "DELETE"
    }),
  composeMessage: (data: { to: string; subject: string; body: string; saveDraft?: boolean; sendViaGmail?: boolean }) =>
    fetchJson<{ success: boolean; isDraft: boolean; folder: string; interaction: InteractionRecord }>(
      "/api/v1/inbox/compose",
      {
        method: "POST",
        body: JSON.stringify(data)
      }
    ),

  // Task 3: Meeting-to-SOW Agent
  listSOWProjects: () => fetchJson<ProjectScope[]>("/api/v1/projects"),
  createSOWFromMeeting: (transcript: string, project_id?: string) =>
    fetchJson<ProjectScope>("/api/v1/projects/from-meeting", {
      method: "POST",
      body: JSON.stringify({ transcript, project_id })
    }),
  getSOWScope: (project_id: string) => fetchJson<ProjectScope>(`/api/v1/projects/${project_id}/scope`),
  getSOWDraftProposal: (project_id: string) =>
    fetchJson<{ project_id: string; version: number; client_ready: boolean; proposal_markdown: string }>(
      `/api/v1/projects/${project_id}/draft-proposal`
    ),
  getSOWClientProposal: (project_id: string) =>
    fetchJson<{ project_id: string; version: number; client_ready: boolean; approved_by: string; approved_at: string; proposal_markdown: string }>(
      `/api/v1/projects/${project_id}/proposal`
    ),
  processSOWFollowUp: (project_id: string, transcript: string) =>
    fetchJson<{ scope: ProjectScope; changes: ScopeChangeSet }>(`/api/v1/projects/${project_id}/follow-up`, {
      method: "POST",
      body: JSON.stringify({ transcript })
    }),
  approveSOWScope: (project_id: string, approved_by: string) =>
    fetchJson<ProjectScope>(`/api/v1/projects/${project_id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by })
    }),
  getSOWExportUrl: (project_id: string, format: string = "html", draft: boolean = false) =>
    `/api/v1/projects/${project_id}/export?format=${format}&draft=${draft}`
};
