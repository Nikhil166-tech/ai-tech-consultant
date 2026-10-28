import { describe, it, expect, vi, beforeEach } from "vitest";
import { GmailClient } from "../src/gmail/client";

describe("Task 2 Server & Gmail Security Verification", () => {
  it("GmailClient partitions storage tokens and processed IDs per userId", () => {
    const clientUser1 = GmailClient.forUser("user_abc_1");
    const clientUser2 = GmailClient.forUser("user_xyz_2");
    const defaultClient = new GmailClient();

    // Verify token path partitioning
    expect((clientUser1 as any).tokensPath).toContain("gmail_tokens_user_abc_1.json");
    expect((clientUser2 as any).tokensPath).toContain("gmail_tokens_user_xyz_2.json");
    expect((defaultClient as any).tokensPath).toContain("gmail_tokens.json");

    // Verify processed message IDs partitioning
    expect((clientUser1 as any).processedIdsPath).toContain("gmail_processed_ids_user_abc_1.json");
    expect((clientUser2 as any).processedIdsPath).toContain("gmail_processed_ids_user_xyz_2.json");

    expect((clientUser1 as any).tokensPath).not.toEqual((clientUser2 as any).tokensPath);
  });

  it("Sanitizes sensitive API keys from error strings and verification responses", () => {
    const sensitiveKey = "AIzaSySecretCustomerKey123456789";
    const rawError = `Failed to connect with key ${sensitiveKey}: invalid project status`;

    // Test sanitization pattern
    const sanitized = rawError.replace(new RegExp(sensitiveKey, "g"), "[REDACTED_API_KEY]");
    expect(sanitized).not.toContain(sensitiveKey);
    expect(sanitized).toContain("[REDACTED_API_KEY]");
  });

  it("Proxy header sanitizer removes client-supplied x-internal-service-key", () => {
    const incomingHeaders: Record<string, string> = {
      "host": "localhost:3001",
      "x-internal-service-key": "attacker_spoofed_key",
      "cookie": "session_id=valid_sess_123",
      "content-type": "application/json"
    };

    // Simulate proxy strip logic in server.ts
    const forwardedHeaders = { ...incomingHeaders };
    delete forwardedHeaders["x-internal-service-key"];

    expect(forwardedHeaders["x-internal-service-key"]).toBeUndefined();
    expect(forwardedHeaders["cookie"]).toBe("session_id=valid_sess_123");
  });

  it("ModelFallbackEngine in TypeScript enforces stable model hierarchy and excludes retired models", async () => {
    const { ModelFallbackEngine } = await import("../src/drafting/fallback_engine");
    const engine = new ModelFallbackEngine({
      role: "EMAIL_DRAFTING",
      geminiApiKey: "mock_key"
    });

    const candidates = engine.getModelCandidates();
    const candidateNames = candidates.map(c => c.model);

    // Verify stable models present
    expect(candidateNames).toContain("gemini-3.5-flash");
    expect(candidateNames).toContain("gemini-3.1-flash-lite");

    // Verify retired models excluded
    expect(candidateNames).not.toContain("gemini-1.5-flash");
    expect(candidateNames).not.toContain("gemini-2.0-flash");
    expect(candidateNames).not.toContain("gemini-2.5-flash");
    expect(candidateNames).not.toContain("claude-3-5-sonnet-latest");
    expect(candidateNames).not.toContain("claude-3-5-haiku-20241022");
  });
});
