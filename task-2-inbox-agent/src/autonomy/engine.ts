import fs from "fs";
import path from "path";
import {
  KindTuple,
  RiskLevel,
  ProductArea,
  AutonomyState,
  HumanReviewRecord,
  AutomaticDeliveryRecord
} from "../types/index.js";

export class AutonomyEngine {
  private stateMap: Map<string, AutonomyState> = new Map();
  private readonly stateFilePath: string;

  constructor(stateFilePath?: string) {
    this.stateFilePath = stateFilePath || path.join(process.cwd(), "data", "autonomy_store.json");
    this.loadState();
  }

  /**
   * Normalizes text for defensible, strict equality comparison.
   * Ignores only insignificant whitespace/line-ending differences.
   * Strictly preserves words, characters, numbers, and punctuation.
   */
  public normalizeText(text: string): string {
    return text
      .split(/\r?\n/)
      .map((line) => line.trim().replace(/[ \t]+/g, " "))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/[\u2018\u2019]/g, "'")
      .replace(/[\u201C\u201D]/g, '"')
      .trim();
  }

  /**
   * Strict equality check: generated draft == final sent reply after normalization.
   */
  public isUnchanged(generatedDraft: string, finalSentReply: string): boolean {
    return this.normalizeText(generatedDraft) === this.normalizeText(finalSentReply);
  }

  public getState(kindKey: string): AutonomyState {
    const existing = this.stateMap.get(kindKey);
    if (existing) {
      return { ...existing };
    }
    const fresh: AutonomyState = {
      kindKey,
      unchangedStreak: 0,
      autonomyEnabled: false,
      totalDrafts: 0,
      totalSentWithoutChanges: 0,
      updatedAt: new Date().toISOString()
    };
    this.stateMap.set(kindKey, fresh);
    return { ...fresh };
  }

  /**
   * Autonomy gating rule:
   * 1. Must be LOW risk.
   * 2. Product area UNKNOWN must NEVER unlock autonomy.
   * 3. Autonomy must be enabled and backed by at least 20 consecutive unchanged human approvals.
   */
  public canAutoSend(kind: KindTuple): boolean {
    if (kind.riskLevel !== RiskLevel.LOW) {
      return false;
    }
    if (kind.productArea === ProductArea.UNKNOWN) {
      return false;
    }
    const state = this.getState(kind.key);
    return state.autonomyEnabled && state.unchangedStreak >= 20;
  }

  /**
   * Records a HUMAN review action.
   * Only human approvals can increment the 20-approval streak.
   */
  public recordHumanReview(review: HumanReviewRecord): AutonomyState {
    const state = this.getState(review.kindKey);
    state.totalDrafts += 1;
    state.updatedAt = new Date().toISOString();

    const isUnknownProductArea = review.kindKey.endsWith(`:${ProductArea.UNKNOWN}`);

    if (review.action === "APPROVE" && review.wasUnchanged) {
      state.unchangedStreak += 1;
      state.totalSentWithoutChanges += 1;

      // UNKNOWN product area must never unlock autonomy
      if (state.unchangedStreak >= 20 && !isUnknownProductArea) {
        state.autonomyEnabled = true;
        state.lastFailureReason = undefined;
      }
    } else {
      const previousAutonomy = state.autonomyEnabled;
      state.unchangedStreak = 0;
      state.autonomyEnabled = false;

      state.lastFailureReason =
        review.action === "REJECT"
          ? `Human rejected draft (${review.notes || "Quality rejection"})`
          : `Human edited draft before sending (${review.diffSummary || "Modified text"})`;

      if (previousAutonomy) {
        console.warn(`[AUTONOMY REVOKED] Kind '${review.kindKey}' autonomy revoked: ${state.lastFailureReason}`);
      }
    }

    this.stateMap.set(review.kindKey, state);
    this.saveState();
    return { ...state };
  }

  // Alias for backward compatibility in tests
  public recordReview(review: HumanReviewRecord): AutonomyState {
    return this.recordHumanReview(review);
  }

  /**
   * Records an AUTOMATIC delivery.
   * CRITICAL: An automatic send NEVER counts as a human approval and does NOT increase unchanged streak.
   */
  public recordAutoDelivery(delivery: AutomaticDeliveryRecord): AutonomyState {
    const state = this.getState(delivery.kindKey);
    state.totalDrafts += 1;
    state.totalSentWithoutChanges += 1;
    // Streak is intentionally NOT incremented
    state.updatedAt = new Date().toISOString();
    this.stateMap.set(delivery.kindKey, state);
    this.saveState();
    return { ...state };
  }

  /**
   * Explicit quality audit revocation pathway.
   * Immediately resets autonomyEnabled to false and streak to 0 with failure reason persisted.
   */
  public revokeAutonomy(kindKey: string, reason: string, revokedBy?: string): AutonomyState {
    const state = this.getState(kindKey);
    state.autonomyEnabled = false;
    state.unchangedStreak = 0;
    state.lastFailureReason = reason;
    state.lastRevokedReason = `${reason}${revokedBy ? ` (by ${revokedBy})` : ""}`;
    state.revokedAt = new Date().toISOString();
    state.updatedAt = new Date().toISOString();
    this.stateMap.set(kindKey, state);
    this.saveState();
    return { ...state };
  }

  public loadState(): void {
    try {
      if (fs.existsSync(this.stateFilePath)) {
        const raw = fs.readFileSync(this.stateFilePath, "utf-8");
        const data = JSON.parse(raw);
        if (Array.isArray(data)) {
          for (const item of data) {
            if (item.kindKey) {
              this.stateMap.set(item.kindKey, item);
            }
          }
        }
      }
    } catch {
      // Fresh in-memory state
    }
  }

  public saveState(): void {
    try {
      const dir = path.dirname(this.stateFilePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      const arrayData = Array.from(this.stateMap.values());
      fs.writeFileSync(this.stateFilePath, JSON.stringify(arrayData, null, 2), "utf-8");
    } catch (err) {
      console.error("Failed to persist autonomy state:", err);
    }
  }

  public resetAll(): void {
    this.stateMap.clear();
    this.saveState();
  }
}
