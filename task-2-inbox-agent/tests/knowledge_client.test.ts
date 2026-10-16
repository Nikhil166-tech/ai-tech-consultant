import { describe, it, expect, vi } from "vitest";
import { Task1KnowledgeClient } from "../src/knowledge/task1_client.js";

describe("Task1KnowledgeClient", () => {
  it("handles network timeout without throwing unhandled exceptions", async () => {
    // Port 9999 with 50ms timeout to simulate unreachable/timeout
    const client = new Task1KnowledgeClient({ baseUrl: "http://127.0.0.1:9999", timeoutMs: 50 });
    const result = await client.askKnowledgeBrain("How do I setup Stripe?");

    expect(result.success).toBe(false);
    expect(result.isAvailable).toBe(false);
    expect(result.needsHumanEscalation).toBe(true);
    expect(result.fallbackReason).toBeDefined();
  });

  it("handles valid Task 1 response and detects insufficient evidence", async () => {
    const client = new Task1KnowledgeClient();
    
    // Mock global fetch to return insufficient evidence response
    vi.spyOn(global, "fetch").mockImplementationOnce(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            answer: "Unknown documentation",
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
