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
  CustomerEmail
} from "./types";

async function fetchJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    credentials: "omit"
  });

  if (!res.ok) {
    let errorMsg = `Request failed (${res.status})`;
    try {
      const errData = await res.json();
      errorMsg = errData.detail || errData.error || errData.message || errorMsg;
    } catch {
      // ignore
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

  // Refresh Runs
  listRefreshRuns: (sitemap_id?: string) =>
    fetchJson<RefreshRunSummary[]>(`/api/v1/refresh-runs${sitemap_id ? `?sitemap_id=${sitemap_id}` : ""}`),
  getRefreshRunDetail: (run_id: string) =>
    fetchJson<{ summary: RefreshRunSummary; urls: RefreshRunUrlItem[] }>(`/api/v1/refresh-runs/${run_id}`),
  triggerRefreshRun: (sitemap_id: string) =>
    fetchJson<RefreshRunSummary>(`/api/v1/sitemaps/${sitemap_id}/trigger-refresh`, {
      method: "POST"
    }),

  // Quarantine
  listQuarantinedArticles: () => fetchJson<QuarantineRecord[]>("/api/v1/quarantine"),
  restoreQuarantinedArticle: (article_id: string) =>
    fetchJson<{ success: boolean; article_id: string }>(`/api/v1/quarantine/${article_id}/restore`, {
      method: "POST"
    }),
  listHealthObservations: () => fetchJson<any[]>("/api/v1/health-observations"),

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
    )
};
