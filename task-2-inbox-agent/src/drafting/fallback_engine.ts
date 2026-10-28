export interface ModelAttemptRecord {
  model: string;
  provider: "google" | "anthropic";
  status: "SUCCESS" | "FAILED" | "VALIDATION_FAILED";
  httpStatus?: number;
  latencyMs: number;
  errorReason?: string;
  tokens: number;
}

export interface ModelExecutionTelemetry {
  modelSelected: string;
  provider: "google" | "anthropic" | "deterministic";
  fallbackOccurred: boolean;
  fallbackReason?: string;
  latencyMs: number;
  totalTokens: number;
  estimatedCostUsd: number;
  attemptsCount: number;
  attemptHistory: ModelAttemptRecord[];
}

export const STABLE_GEMINI_MODELS = [
  "gemini-3.5-flash",
  "gemini-3.5-flash-lite",
  "gemini-3.1-flash-lite",
  "gemini-flash-latest",
  "gemini-flash-lite-latest"
];

export const PREVIEW_GEMINI_MODELS = [
  "gemini-3-flash-preview",
  "gemini-3.1-pro-preview"
];

export const STABLE_CLAUDE_MODELS = [
  "claude-haiku-5-5",
  "claude-sonnet-5-5",
  "claude-opus-5-5",
  "claude-sonnet-4-6",
  "claude-haiku-4-5-20251001"
];

export const DEPRECATED_MODELS = new Set([
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
  "gemini-2.0-flash",
  "gemini-1.5-flash",
  "gemini-1.5-pro",
  "claude-3-7-sonnet-latest",
  "claude-3-5-sonnet-latest",
  "claude-3-5-haiku-latest",
  "claude-3-haiku-20240307",
  "claude-3-5-sonnet-20241022",
  "claude-3-5-haiku-20241022"
]);

const ESTIMATED_COST_PER_1K: Record<string, number> = {
  "gemini-3.5-flash": 0.0001,
  "gemini-3.5-flash-lite": 0.00005,
  "gemini-3.1-flash-lite": 0.00005,
  "gemini-flash-latest": 0.0001,
  "gemini-3-flash-preview": 0.0001,
  "claude-haiku-5-5": 0.0008,
  "claude-sonnet-5-5": 0.003,
  "claude-opus-5-5": 0.015
};

export interface FallbackEngineOptions {
  role?: string;
  geminiApiKey?: string;
  anthropicApiKey?: string;
  anthropicWorkspaceId?: string;
  maxAttempts?: number;
  totalTimeoutSeconds?: number;
  requestTimeoutSeconds?: number;
}

export class ModelFallbackEngine {
  public readonly role: string;
  private readonly geminiApiKey: string;
  private readonly anthropicApiKey: string;
  private readonly anthropicWorkspaceId: string;
  private readonly maxAttempts: number;
  private readonly totalTimeoutSeconds: number;
  private readonly requestTimeoutSeconds: number;
  private readonly allowPreviewModels: boolean;

  constructor(options: FallbackEngineOptions = {}) {
    this.role = options.role || "EMAIL_DRAFTING";
    this.geminiApiKey = options.geminiApiKey || process.env.GEMINI_API_KEY || "";
    this.anthropicApiKey = options.anthropicApiKey || process.env.ANTHROPIC_API_KEY || "";
    this.anthropicWorkspaceId = options.anthropicWorkspaceId || process.env.ANTHROPIC_WORKSPACE_ID || "";
    this.maxAttempts = parseInt(process.env.MAX_FALLBACK_ATTEMPTS || String(options.maxAttempts || 3), 10);
    this.totalTimeoutSeconds = parseFloat(process.env.TOTAL_TIMEOUT_SECONDS || String(options.totalTimeoutSeconds || 15.0));
    this.requestTimeoutSeconds = parseFloat(process.env.REQUEST_TIMEOUT_SECONDS || String(options.requestTimeoutSeconds || 5.0));
    this.allowPreviewModels = ["true", "1", "yes"].includes((process.env.ALLOW_PREVIEW_MODELS || "false").toLowerCase());
  }

  public getModelCandidates(): Array<{ provider: "google" | "anthropic"; model: string }> {
    let primaryEnv = "";
    let fallbacksEnv = "";

    const role = (this.role || "EMAIL_DRAFTING").toUpperCase();
    if (role === "EMAIL_CLASSIFICATION") {
      primaryEnv = process.env.MODEL_CLASSIFICATION || process.env.MODEL_EMAIL_CLASSIFICATION || "gemini-3.5-flash";
      fallbacksEnv = process.env.MODEL_CLASSIFICATION_FALLBACKS || process.env.MODEL_EMAIL_CLASSIFICATION_FALLBACKS || "";
    } else if (role === "EMAIL_DRAFTING") {
      primaryEnv = process.env.MODEL_DRAFTING || process.env.MODEL_EMAIL_DRAFTING || process.env.GEMINI_MODEL || "gemini-3.5-flash";
      fallbacksEnv = process.env.MODEL_DRAFTING_FALLBACKS || process.env.MODEL_EMAIL_DRAFTING_FALLBACKS || "";
    } else if (role === "KNOWLEDGE_ANSWER" || role === "KB_ANSWER") {
      primaryEnv = process.env.MODEL_KNOWLEDGE_ANSWER || process.env.MODEL_KB_ANSWER || "gemini-3.5-flash";
      fallbacksEnv = process.env.MODEL_KNOWLEDGE_ANSWER_FALLBACKS || process.env.MODEL_KB_ANSWER_FALLBACKS || "";
    } else if (role === "REQUIREMENTS_EXTRACTION") {
      primaryEnv = process.env.MODEL_REQUIREMENTS_EXTRACTION || "claude-haiku-5-5";
      fallbacksEnv = process.env.MODEL_REQUIREMENTS_EXTRACTION_FALLBACKS || "";
    } else if (role === "CAPABILITY_CHECKING") {
      primaryEnv = process.env.MODEL_CAPABILITY_CHECKING || "gemini-3.5-flash";
      fallbacksEnv = process.env.MODEL_CAPABILITY_CHECKING_FALLBACKS || "";
    } else {
      primaryEnv = process.env.MODEL_PRIMARY || process.env.GEMINI_MODEL || "gemini-3.5-flash";
      fallbacksEnv = process.env.MODEL_FALLBACKS || "";
    }

    const fallbackList = fallbacksEnv
      ? fallbacksEnv.split(",").map((s) => s.trim()).filter(Boolean)
      : [
          "gemini-3.5-flash-lite",
          "gemini-3.1-flash-lite",
          "gemini-flash-latest",
          "claude-haiku-5-5",
          "claude-sonnet-5-5"
        ];

    if (this.allowPreviewModels && !fallbacksEnv) {
      fallbackList.splice(1, 0, "gemini-3-flash-preview");
    }

    const raw = [primaryEnv, ...fallbackList];
    const result: Array<{ provider: "google" | "anthropic"; model: string }> = [];
    const seen = new Set<string>();

    for (let i = 0; i < raw.length; i++) {
      const m = raw[i];
      if (!m || seen.has(m)) continue;
      seen.add(m);

      if (DEPRECATED_MODELS.has(m) && i > 0) continue;
      if (m.includes("-preview") && !this.allowPreviewModels && i > 0) continue;

      const provider = m.toLowerCase().includes("claude") ? "anthropic" : "google";
      result.push({ provider, model: m });
    }

    return result;
  }

  private isNonRetryableError(status: number, text: string): { fatal: boolean; reason: string } {
    const lower = text.toLowerCase();
    if (status === 401 || status === 403) {
      return { fatal: true, reason: `Authentication/permission failure (HTTP ${status})` };
    }
    if (status === 400) {
      if (lower.includes("api key not valid") || lower.includes("api_key_invalid") || lower.includes("invalid x-api-key")) {
        return { fatal: true, reason: "Invalid API key" };
      }
      if (lower.includes("credit balance is too low") || lower.includes("plans & billing")) {
        return { fatal: true, reason: "Account billing credit exhausted" };
      }
      if (lower.includes("quota exceeded") || lower.includes("billing not enabled")) {
        return { fatal: true, reason: "Quota/billing disabled" };
      }
    }
    return { fatal: false, reason: "" };
  }

  private isQuotaExhaustedRateLimit(status: number, text: string): boolean {
    if (status === 429) {
      const lower = text.toLowerCase();
      if (lower.includes("resource_exhausted") || lower.includes("quota") || lower.includes("credit") || lower.includes("daily")) {
        return true;
      }
    }
    return false;
  }

  public async executeWithFallback(
    systemPrompt: string,
    userPrompt: string,
    validateFn?: (text: string) => { valid: boolean; error?: string }
  ): Promise<{ text: string | null; telemetry: ModelExecutionTelemetry }> {
    const startTime = Date.now();
    const telemetry: ModelExecutionTelemetry = {
      modelSelected: "none",
      provider: "none",
      fallbackOccurred: false,
      latencyMs: 0,
      totalTokens: 0,
      estimatedCostUsd: 0,
      attemptsCount: 0,
      attemptHistory: []
    };

    const candidates = this.getModelCandidates();
    const invalidProviders = new Set<string>();
    const exhaustedProviders = new Set<string>();
    let attemptIdx = 0;

    for (const { provider, model } of candidates) {
      if (attemptIdx >= this.maxAttempts) {
        telemetry.fallbackReason = telemetry.fallbackReason || `Exceeded maximum attempts limit (${this.maxAttempts})`;
        break;
      }

      const elapsedSec = (Date.now() - startTime) / 1000.0;
      if (elapsedSec >= this.totalTimeoutSeconds) {
        telemetry.fallbackReason = telemetry.fallbackReason || `Exceeded deadline (${this.totalTimeoutSeconds}s)`;
        break;
      }

      if (invalidProviders.has(provider) || exhaustedProviders.has(provider)) {
        continue;
      }

      if (provider === "google" && (!this.geminiApiKey || this.geminiApiKey.startsWith("sk-ant-"))) {
        continue;
      }
      if (provider === "anthropic" && !this.anthropicApiKey) {
        continue;
      }

      attemptIdx++;
      telemetry.attemptsCount = attemptIdx;
      const attemptStart = Date.now();

      const { text, status, error, tokens } = await this.callWithRetry(
        provider,
        model,
        systemPrompt,
        userPrompt,
        startTime + this.totalTimeoutSeconds * 1000
      );

      const attemptLatency = Date.now() - attemptStart;
      const attemptRec: ModelAttemptRecord = {
        model,
        provider,
        status: text ? "SUCCESS" : "FAILED",
        httpStatus: status,
        latencyMs: attemptLatency,
        errorReason: error,
        tokens
      };
      telemetry.attemptHistory.push(attemptRec);

      if (text) {
        if (validateFn) {
          const valResult = validateFn(text);
          if (!valResult.valid) {
            telemetry.fallbackOccurred = true;
            telemetry.fallbackReason = `Structured validation failed: ${valResult.error}`;
            attemptRec.status = "VALIDATION_FAILED";
            attemptRec.errorReason = valResult.error;
            continue;
          }
        }

        telemetry.modelSelected = model;
        telemetry.provider = provider;
        telemetry.latencyMs = Date.now() - startTime;
        telemetry.totalTokens = tokens;
        const rate = ESTIMATED_COST_PER_1K[model] || 0.0001;
        telemetry.estimatedCostUsd = Math.round((tokens / 1000.0) * rate * 1e6) / 1e6;
        if (attemptIdx > 1) telemetry.fallbackOccurred = true;

        return { text, telemetry };
      }

      telemetry.fallbackOccurred = true;
      telemetry.fallbackReason = telemetry.fallbackReason || `Model '${model}' failed (HTTP ${status}): ${error}`;

      const fatalCheck = this.isNonRetryableError(status || 0, error || "");
      if (fatalCheck.fatal) {
        invalidProviders.add(provider);
        continue;
      }

      if (this.isQuotaExhaustedRateLimit(status || 0, error || "")) {
        exhaustedProviders.add(provider);
        continue;
      }
    }

    telemetry.modelSelected = "deterministic_fallback";
    telemetry.provider = "deterministic";
    telemetry.latencyMs = Date.now() - startTime;
    return { text: null, telemetry };
  }

  private async callWithRetry(
    provider: "google" | "anthropic",
    model: string,
    systemPrompt: string,
    userPrompt: string,
    deadlineEpochMs: number
  ): Promise<{ text: string | null; status?: number; error?: string; tokens: number }> {
    const remainingMs = Math.max(500, Math.min(this.requestTimeoutSeconds * 1000, deadlineEpochMs - Date.now()));

    for (let retry = 0; retry < 2; retry++) {
      try {
        if (provider === "google") {
          return await this.callGemini(model, systemPrompt, userPrompt, remainingMs);
        } else {
          return await this.callClaude(model, systemPrompt, userPrompt, remainingMs);
        }
      } catch (err: any) {
        if (retry === 0 && deadlineEpochMs - Date.now() > 1500) {
          const jitter = Math.random() * 100 + 50;
          await new Promise((r) => setTimeout(r, 200 * Math.pow(2, retry) + jitter));
          continue;
        }
        return { text: null, status: 408, error: err?.message || "Timeout/network error", tokens: 0 };
      }
    }

    return { text: null, status: 500, error: "Transient retries exhausted", tokens: 0 };
  }

  private async callGemini(
    model: string,
    systemPrompt: string,
    userPrompt: string,
    timeoutMs: number
  ): Promise<{ text: string | null; status?: number; error?: string; tokens: number }> {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${this.geminiApiKey}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ role: "user", parts: [{ text: userPrompt }] }],
          systemInstruction: { parts: [{ text: systemPrompt }] },
          generationConfig: { temperature: 0.2, maxOutputTokens: 600 }
        }),
        signal: controller.signal
      });

      clearTimeout(timer);

      if (res.ok) {
        const data: any = await res.json();
        const rawText = data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || null;
        const totalTok = data?.usageMetadata?.totalTokenCount || (rawText ? rawText.split(/\s+/).length * 2 : 0);
        return { text: rawText, status: 200, tokens: totalTok };
      }

      const errText = await res.text().catch(() => "");
      return { text: null, status: res.status, error: errText.slice(0, 240), tokens: 0 };
    } finally {
      clearTimeout(timer);
    }
  }

  private async callClaude(
    model: string,
    systemPrompt: string,
    userPrompt: string,
    timeoutMs: number
  ): Promise<{ text: string | null; status?: number; error?: string; tokens: number }> {
    const headers: Record<string, string> = {
      "x-api-key": this.anthropicApiKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json"
    };
    if (this.anthropicWorkspaceId) {
      headers["anthropic-workspace-id"] = this.anthropicWorkspaceId;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers,
        body: JSON.stringify({
          model,
          max_tokens: 600,
          system: systemPrompt,
          messages: [{ role: "user", content: userPrompt }]
        }),
        signal: controller.signal
      });

      clearTimeout(timer);

      if (res.ok) {
        const data: any = await res.json();
        const rawText = data?.content?.[0]?.text?.trim() || null;
        const totalTok = (data?.usage?.input_tokens || 0) + (data?.usage?.output_tokens || 0);
        return { text: rawText, status: 200, tokens: totalTok };
      }

      const errText = await res.text().catch(() => "");
      return { text: null, status: res.status, error: errText.slice(0, 240), tokens: 0 };
    } finally {
      clearTimeout(timer);
    }
  }
}
