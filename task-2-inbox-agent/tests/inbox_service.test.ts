import { describe, it, expect, beforeEach } from "vitest";
import { InboxService } from "../src/inbox_service.js";
import { CustomerEmail } from "../src/types/index.js";
import { AutonomyEngine } from "../src/autonomy/engine.js";
import { FeedbackStore } from "../src/feedback/store.js";
import path from "path";
import fs from "fs";

describe("InboxService End-to-End", () => {
  let inbox: InboxService;
  const testStateFile = path.join(process.cwd(), "data", "test_inbox_autonomy.json");
  const testFeedbackFile = path.join(process.cwd(), "data", "test_inbox_feedback.json");

  beforeEach(() => {
    if (fs.existsSync(testStateFile)) {
      fs.unlinkSync(testStateFile);
    }
    if (fs.existsSync(testFeedbackFile)) {
      fs.unlinkSync(testFeedbackFile);
    }
    const autonomyEngine = new AutonomyEngine(testStateFile);
    const feedbackStore = new FeedbackStore(testFeedbackFile);
    autonomyEngine.resetAll();
    feedbackStore.clear();

    inbox = new InboxService({ autonomyEngine, feedbackStore });
  });

  it("routes high-risk financial refund inquiry to human review queue", async () => {
    const email: CustomerEmail = {
      id: "em_refund_01",
      senderEmail: "customer@corp.com",
      senderName: "Alice",
      subject: "Unauthorized charge - please refund $99",
      body: "I was charged $99 by mistake. Please refund my card.",
      receivedAt: new Date().toISOString()
    };

    const result = await inbox.processEmail(email);
    expect(result.routedTo).toBe("HUMAN_REVIEW_QUEUE");
    expect(result.draft.autoSendEligible).toBe(false);
    expect(result.classification.riskFlags).toContain("FINANCIAL_DISPUTE_OR_REFUND");
  });

  it("human review lifecycle: approve unchanged increments streak, review removes from pending", async () => {
    const email: CustomerEmail = {
      id: "em_stripe_01",
      senderEmail: "webmaster@directory.com",
      senderName: "Bob",
      subject: "Stripe Publishable Key",
      body: "Where do I input our Stripe keys in admin?",
      receivedAt: new Date().toISOString()
    };

    // 1. Process email -> placed in pending queue
    const result = await inbox.processEmail(email);
    expect(result.routedTo).toBe("HUMAN_REVIEW_QUEUE");
    expect(inbox.getPendingDrafts().length).toBe(1);

    // 2. Human reviews and approves without edits
    const reviewRecord = inbox.reviewDraft(email.id, "APPROVE", undefined, "expert_reviewer");
    expect(reviewRecord.action).toBe("APPROVE");
    expect(reviewRecord.wasUnchanged).toBe(true);

    // 3. Removed from pending queue
    expect(inbox.getPendingDrafts().length).toBe(0);

    // 4. Streak incremented
    const state = inbox.autonomyEngine.getState(result.classification.kind.key);
    expect(state.unchangedStreak).toBe(1);
  });
});
