import { Task1AskResponse } from "../types/index.js";
import { Task1AskResponseSchema } from "../validation/schemas.js";

export interface Task1ClientOptions {
  baseUrl?: string;
  timeoutMs?: number;
}

export interface Task1ClientResult {
  success: boolean;
  response?: Task1AskResponse;
  isAvailable: boolean;
  needsHumanEscalation: boolean;
  fallbackReason?: string;
}

/**
 * Typed HTTP REST client for querying the Task 1 Knowledge Brain API.
 * Features configurable timeout, graceful offline fallback, and strict Zod contract validation.
 */
export class Task1KnowledgeClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: Task1ClientOptions = {}) {
    this.baseUrl = options.baseUrl || process.env.TASK1_API_URL || "http://127.0.0.1:8000";
    this.timeoutMs = options.timeoutMs || 4000;
  }

  public async askKnowledgeBrain(
    question: string,
    categoryFilter?: string
  ): Promise<Task1ClientResult> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const internalKey = process.env.INTERNAL_SERVICE_KEY || "";
      const res = await fetch(`${this.baseUrl}/api/v1/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Service-Key": internalKey
        },
        body: JSON.stringify({
          question,
          category_filter: categoryFilter || null,
          history: []
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!res.ok) {
        return {
          success: false,
          isAvailable: false,
          needsHumanEscalation: true,
          fallbackReason: `Task 1 returned HTTP ${res.status}`
        };
      }

      const rawData = await res.json();

      // Strict Zod schema validation
      const parseResult = Task1AskResponseSchema.safeParse(rawData);
      if (!parseResult.success) {
        const errorDetails = parseResult.error.errors.map((e) => `${e.path.join(".")}: ${e.message}`).join("; ");
        return {
          success: false,
          isAvailable: true,
          needsHumanEscalation: true,
          fallbackReason: `Task 1 response failed contract schema validation (${errorDetails})`
        };
      }

      const data = parseResult.data as Task1AskResponse;

      // Check evidence confidence
      const needsHumanEscalation =
        data.needs_human_review ||
        !data.is_known ||
        data.evidence_status === "INSUFFICIENT" ||
        data.evidence_status === "NONE";

      return {
        success: true,
        response: data,
        isAvailable: true,
        needsHumanEscalation,
        fallbackReason: needsHumanEscalation
          ? `Task 1 reported insufficient verified documentation (evidence_score=${data.evidence_score})`
          : undefined
      };
    } catch (err: any) {
      clearTimeout(timeoutId);
      const isTimeout = err?.name === "AbortError";
      return {
        success: false,
        isAvailable: false,
        needsHumanEscalation: true,
        fallbackReason: isTimeout
          ? `Task 1 Knowledge Brain request timed out after ${this.timeoutMs}ms`
          : `Task 1 Knowledge Brain unavailable: ${err?.message || "connection failed"}`
      };
    }
  }
}
