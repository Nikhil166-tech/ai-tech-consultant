import { describe, it, expect, beforeEach } from "vitest";
import { AutonomyEngine } from "../src/autonomy/engine.js";
import { Intent, RiskLevel, ProductArea, formatKindKey, HumanReviewRecord } from "../src/types/index.js";
import fs from "fs";
import path from "path";

describe("AutonomyEngine", () => {
  const testStateFile = path.join(process.cwd(), "data", "test_autonomy_store.json");
  let engine: AutonomyEngine;

  beforeEach(() => {
    if (fs.existsSync(testStateFile)) {
      fs.unlinkSync(testStateFile);
    }
    engine = new AutonomyEngine(testStateFile);
  });

  it("strict unchanged check: normalizes only whitespace, rejects wording edits", () => {
    const draft = "Hello John,\n\nPlease go to Finance > Payment Gateways.\n\nBest regards,\nSupport";
    const identicalWithWhitespace = "Hello John,  \n\nPlease go to Finance > Payment Gateways.  \n\nBest regards,\nSupport";
    const editedReply = "Hello John,\n\nPlease go to Finance > Gateways immediately.\n\nBest regards,\nSupport";

    expect(engine.isUnchanged(draft, identicalWithWhitespace)).toBe(true);
    expect(engine.isUnchanged(draft, editedReply)).toBe(false);
  });

  it("gating: requires 20 consecutive unchanged reviews to enable autonomy", () => {
    const kindKey = formatKindKey(Intent.HOW_TO_CONFIGURE, RiskLevel.LOW, ProductArea.PAYMENTS_GATEWAYS);
    const kind = {
      intent: Intent.HOW_TO_CONFIGURE,
      riskLevel: RiskLevel.LOW,
      productArea: ProductArea.PAYMENTS_GATEWAYS,
      key: kindKey
    };

    // 1-19 consecutive unchanged reviews: autonomy should remain false
    for (let i = 1; i <= 19; i++) {
      const review: HumanReviewRecord = {
        id: `rev_${i}`,
        emailId: `em_${i}`,
        draftId: `dr_${i}`,
        kindKey,
        action: "APPROVE",
        originalDraft: "Base text",
        finalSentReply: "Base text",
        wasUnchanged: true,
        reviewerId: "agent_1",
        reviewedAt: new Date().toISOString()
      };
      const state = engine.recordReview(review);
      expect(state.unchangedStreak).toBe(i);
      expect(state.autonomyEnabled).toBe(false);
      expect(engine.canAutoSend(kind)).toBe(false);
    }

    // 20th consecutive unchanged review: autonomy unlocks!
    const review20: HumanReviewRecord = {
      id: "rev_20",
      emailId: "em_20",
      draftId: "dr_20",
      kindKey,
      action: "APPROVE",
      originalDraft: "Base text",
      finalSentReply: "Base text",
      wasUnchanged: true,
      reviewerId: "agent_1",
      reviewedAt: new Date().toISOString()
    };
    const state20 = engine.recordReview(review20);
    expect(state20.unchangedStreak).toBe(20);
    expect(state20.autonomyEnabled).toBe(true);
    expect(engine.canAutoSend(kind)).toBe(true);
  });

  it("immediate revocation: an edit resets streak to 0 and disables autonomy instantly", () => {
    const kindKey = formatKindKey(Intent.HOW_TO_CONFIGURE, RiskLevel.LOW, ProductArea.PAYMENTS_GATEWAYS);
    const kind = {
      intent: Intent.HOW_TO_CONFIGURE,
      riskLevel: RiskLevel.LOW,
      productArea: ProductArea.PAYMENTS_GATEWAYS,
      key: kindKey
    };

    // Fast-forward to 20 unchanged reviews
    for (let i = 1; i <= 20; i++) {
      engine.recordReview({
        id: `rev_${i}`,
        emailId: `em_${i}`,
        draftId: `dr_${i}`,
        kindKey,
        action: "APPROVE",
        originalDraft: "Base text",
        finalSentReply: "Base text",
        wasUnchanged: true,
        reviewerId: "agent_1",
        reviewedAt: new Date().toISOString()
      });
    }
    expect(engine.canAutoSend(kind)).toBe(true);

    // Review 21 has an edit: autonomy must instantly revoke!
    const editReview: HumanReviewRecord = {
      id: "rev_21",
      emailId: "em_21",
      draftId: "dr_21",
      kindKey,
      action: "EDIT",
      originalDraft: "Base text",
      finalSentReply: "Base text with human modification",
      wasUnchanged: false,
      diffSummary: "Human changed wording",
      reviewerId: "agent_1",
      reviewedAt: new Date().toISOString()
    };
    const revokedState = engine.recordReview(editReview);
    expect(revokedState.autonomyEnabled).toBe(false);
    expect(revokedState.unchangedStreak).toBe(0);
    expect(engine.canAutoSend(kind)).toBe(false);
  });

  it("high-risk kinds are never eligible for auto-send even with high streak", () => {
    const highRiskKind = {
      intent: Intent.BILLING_ISSUE,
      riskLevel: RiskLevel.HIGH,
      productArea: ProductArea.PAYMENTS_GATEWAYS,
      key: formatKindKey(Intent.BILLING_ISSUE, RiskLevel.HIGH, ProductArea.PAYMENTS_GATEWAYS)
    };

    expect(engine.canAutoSend(highRiskKind)).toBe(false);
  });
});
