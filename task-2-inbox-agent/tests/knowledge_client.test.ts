import { describe, it, expect, vi, afterEach } from "vitest";
import { Task1KnowledgeClient } from "../src/knowledge/task1_client.js";

describe("Task1KnowledgeClient", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("handles Task 1 timeout gracefully without throwing unhandled exceptions", async () => {
    const client = new Task1KnowledgeClient({ baseUrl: "http://127.0.0.1:9999", timeoutMs: 30 });
    
    // Simulate abort error
    vi.spyOn(global, "fetch").mockImplementationOnce((_url, options: any) => {
      return new Promise((_, reject) => {
        const timeout = setTimeout(() => {
          const abortErr = new Error("The operation was aborted");
          abortErr.name = "AbortError";
          reject(abortErr);
        }, 10);
      });
    });

    const result = await client.askKnowledgeBrain("How do I setup Stripe?");
    expect(result.success).toBe(false);
    expect(result.isAvailable).toBe(false);
    expect(result.needsHumanEscalation).toBe(true);
    expect(result.fallbackReason).toContain("timed out");
  });

  it("safely handles malformed Task 1 response using strict Zod validation", async () => {
    const client = new Task1KnowledgeClient();

    // Mock malformed response missing required fields or having invalid types
    vi.spyOn(global, "fetch").mockImplementationOnce(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            // Missing 'answer' string
            citations: "not-an-array",
            evidence_score: "invalid-string-score"
          })
      } as any)
    );

    const result = await client.askKnowledgeBrain("How to connect domain");
    expect(result.success).toBe(false);
    expect(result.isAvailable).toBe(true);
    expect(result.needsHumanEscalation).toBe(true);
    expect(result.fallbackReason).toContain("failed contract schema validation");
  });

  it("handles valid Task 1 response and flags insufficient evidence for human escalation", async () => {
    const client = new Task1KnowledgeClient();
    
    vi.spyOn(global, "fetch").mockImplementationOnce(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            answer: "No verified documentation in Solution Center.",
            citations: [],
            evidence_score: 0.12,
            evidence_status: "INSUFFICIENT",
            is_known: false,
            needs_human_review: true,
            visual_references: []
          })
      } as any)
    );

    const result = await client.askKnowledgeBrain("Unreleased quantum feature");
    expect(result.success).toBe(true);
    expect(result.needsHumanEscalation).toBe(true);
    expect(result.fallbackReason).toContain("insufficient verified documentation");
  });
});
