import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { AutonomyEngine } from "../src/autonomy/engine.js";
import { Intent, RiskLevel, ProductArea, formatKindKey, HumanReviewRecord, AutomaticDeliveryRecord } from "../src/types/index.js";
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

  afterEach(() => {
    if (fs.existsSync(testStateFile)) {
      fs.unlinkSync(testStateFile);
    }
  });

  it("strict unchanged check: normalizes only whitespace, rejects wording edits", () => {
    const draft = "Hello John,\n\nPlease go to Finance > Payment Gateways.\n\nBest regards,\nSupport";
    const identicalWithWhitespace = "Hello John,  \n\nPlease go to Finance > Payment Gateways.  \n\nBest regards,\nSupport";
    const editedReply = "Hello John,\n\nPlease go to Finance > Gateways immediately.\n\nBest regards,\nSupport";

    expect(engine.isUnchanged(draft, identicalWithWhitespace)).toBe(true);
    expect(engine.isUnchanged(draft, editedReply)).toBe(false);
  });

  it("20 human approvals unlock autonomy for low-risk, known product areas", () => {
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
        reviewerId: "specialist_1",
        reviewedAt: new Date().toISOString()
      };
      const state = engine.recordHumanReview(review);
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
      reviewerId: "specialist_1",
      reviewedAt: new Date().toISOString()
    };
    const state20 = engine.recordHumanReview(review20);
    expect(state20.unchangedStreak).toBe(20);
    expect(state20.autonomyEnabled).toBe(true);
    expect(engine.canAutoSend(kind)).toBe(true);
  });

  it("unknown product area cannot auto-send even after 20 unchanged approvals", () => {
    const unknownKindKey = formatKindKey(Intent.HOW_TO_CONFIGURE, RiskLevel.LOW, ProductArea.UNKNOWN);
    const unknownKind = {
      intent: Intent.HOW_TO_CONFIGURE,
      riskLevel: RiskLevel.LOW,
      productArea: ProductArea.UNKNOWN,
      key: unknownKindKey
    };

    for (let i = 1; i <= 25; i++) {
      engine.recordHumanReview({
        id: `rev_unk_${i}`,
        emailId: `em_unk_${i}`,
        draftId: `dr_unk_${i}`,
        kindKey: unknownKindKey,
        action: "APPROVE",
        originalDraft: "Uncertain topic text",
        finalSentReply: "Uncertain topic text",
        wasUnchanged: true,
        reviewerId: "specialist_1",
        reviewedAt: new Date().toISOString()
      });
    }

    const state = engine.getState(unknownKindKey);
    expect(state.unchangedStreak).toBe(25);
    // UNKNOWN product area must NEVER unlock autonomy
    expect(state.autonomyEnabled).toBe(false);
    expect(engine.canAutoSend(unknownKind)).toBe(false);
  });

  it("AUTO_SENT does not count as human approval and does not increase streak", () => {
    const kindKey = formatKindKey(Intent.HOW_TO_CONFIGURE, RiskLevel.LOW, ProductArea.DOMAINS_DNS);
    const kind = {
      intent: Intent.HOW_TO_CONFIGURE,
      riskLevel: RiskLevel.LOW,
      productArea: ProductArea.DOMAINS_DNS,
      key: kindKey
    };

    // Reach 20 human reviews
    for (let i = 1; i <= 20; i++) {
      engine.recordHumanReview({
        id: `rev_h_${i}`,
        emailId: `em_h_${i}`,
        draftId: `dr_h_${i}`,
        kindKey,
        action: "APPROVE",
        originalDraft: "DNS setup guide",
        finalSentReply: "DNS setup guide",
        wasUnchanged: true,
        reviewerId: "human_reviewer",
        reviewedAt: new Date().toISOString()
      });
    }
    expect(engine.getState(kindKey).unchangedStreak).toBe(20);
    expect(engine.canAutoSend(kind)).toBe(true);

    // Now an automatic delivery occurs
    const autoDelivery: AutomaticDeliveryRecord = {
      id: "auto_deliv_01",
      interactionId: "inter_01",
      emailId: "em_auto_01",
      draftId: "dr_auto_01",
      kindKey,
      sentReply: "DNS setup guide",
      sentAt: new Date().toISOString(),
      promptVersion: "v1_baseline"
    };

    const afterAutoState = engine.recordAutoDelivery(autoDelivery);
    // Streak must NOT have incremented!
    expect(afterAutoState.unchangedStreak).toBe(20);
    expect(afterAutoState.totalSentWithoutChanges).toBe(21);
  });

  it("explicit quality failure revokes autonomy immediately and resets streak to 0", () => {
    const kindKey = formatKindKey(Intent.HOW_TO_CONFIGURE, RiskLevel.LOW, ProductArea.EMAIL_TEMPLATES);
    const kind = {
      intent: Intent.HOW_TO_CONFIGURE,
      riskLevel: RiskLevel.LOW,
      productArea: ProductArea.EMAIL_TEMPLATES,
      key: kindKey
    };

    // Unlock autonomy with 20 approvals
    for (let i = 1; i <= 20; i++) {
      engine.recordHumanReview({
        id: `rev_${i}`,
        emailId: `em_${i}`,
        draftId: `dr_${i}`,
        kindKey,
        action: "APPROVE",
        originalDraft: "Template guidance",
        finalSentReply: "Template guidance",
        wasUnchanged: true,
        reviewerId: "agent_1",
        reviewedAt: new Date().toISOString()
      });
    }
    expect(engine.canAutoSend(kind)).toBe(true);

    // Explicit quality audit failure
    const revokedState = engine.revokeAutonomy(
      kindKey,
      "Customer CSAT dropped below 85% in weekly spot audit",
      "qa_lead_carol"
    );

    expect(revokedState.autonomyEnabled).toBe(false);
    expect(revokedState.unchangedStreak).toBe(0);
    expect(revokedState.lastFailureReason).toBe("Customer CSAT dropped below 85% in weekly spot audit");
    expect(revokedState.lastRevokedReason).toContain("qa_lead_carol");
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
