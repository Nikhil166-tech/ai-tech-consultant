import fs from "fs";
import path from "path";
import {
  KindTuple,
  RiskLevel,
  AutonomyState,
  HumanReviewRecord
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

  public canAutoSend(kind: KindTuple): boolean {
    if (kind.riskLevel !== RiskLevel.LOW) {
      return false;
    }
    const state = this.getState(kind.key);
    return state.autonomyEnabled && state.unchangedStreak >= 20;
  }

  public recordReview(review: HumanReviewRecord): AutonomyState {
    const state = this.getState(review.kindKey);
    state.totalDrafts += 1;
    state.updatedAt = new Date().toISOString();

    if (review.action === "APPROVE" && review.wasUnchanged) {
      state.unchangedStreak += 1;
      state.totalSentWithoutChanges += 1;

      if (state.unchangedStreak >= 20) {
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

  public revokeAutonomy(kindKey: string, reason: string): AutonomyState {
    const state = this.getState(kindKey);
    state.autonomyEnabled = false;
    state.unchangedStreak = 0;
    state.lastFailureReason = reason;
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
