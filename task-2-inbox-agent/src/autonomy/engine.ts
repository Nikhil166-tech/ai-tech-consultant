import fs from "fs";
import path from "path";
import {
  KindTuple,
  RiskLevel,
  ProductArea,
  AutonomyState,
  LabelAutonomyState,
  AutonomyGlobalSettings,
  HumanReviewRecord,
  AutomaticDeliveryRecord
} from "../types/index.js";

export class AutonomyEngine {
  private stateMap: Map<string, AutonomyState> = new Map();
  private labelStateMap: Map<string, LabelAutonomyState> = new Map();
  private globalSettings: AutonomyGlobalSettings = {
    defaultThreshold: 3,
    emergencyStop: false,
    requireGmailConnection: false,
    minEvidenceScore: 0.4,
    updatedAt: new Date().toISOString()
  };

  private readonly stateFilePath: string;
  private readonly labelStateFilePath: string;
  private readonly settingsFilePath: string;

  constructor(stateFilePath?: string) {
    this.stateFilePath = stateFilePath || path.join(process.cwd(), "data", "autonomy_store.json");
    const baseDir = path.dirname(this.stateFilePath);
    const baseName = path.basename(this.stateFilePath, ".json");
    this.labelStateFilePath = path.join(baseDir, `${baseName}_labels.json`);
    this.settingsFilePath = path.join(baseDir, `${baseName}_settings.json`);
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

  public getLabelState(labelKey: string): LabelAutonomyState {
    const existing = this.labelStateMap.get(labelKey);
    if (existing) {
      return { ...existing };
    }
    const parts = labelKey.split(" -> ");
    const parentSettingType = parts[0] || "General Settings";
    const specificLabel = parts[1] || parts[0] || "General";

    const fresh: LabelAutonomyState = {
      labelKey,
      parentSettingType,
      specificLabel,
      unchangedStreak: 0,
      requiredThreshold: this.globalSettings.defaultThreshold,
      autonomyEnabled: false,
      disabledByUser: false,
      totalDrafts: 0,
      totalSentWithoutChanges: 0,
      updatedAt: new Date().toISOString()
    };
    this.labelStateMap.set(labelKey, fresh);
    return { ...fresh };
  }

  public getAllLabelStates(): LabelAutonomyState[] {
    return Array.from(this.labelStateMap.values());
  }

  public getGlobalSettings(): AutonomyGlobalSettings {
    return { ...this.globalSettings };
  }

  public updateGlobalSettings(settings: Partial<AutonomyGlobalSettings>): AutonomyGlobalSettings {
    this.globalSettings = {
      ...this.globalSettings,
      ...settings,
      updatedAt: new Date().toISOString()
    };
    this.saveState();
    return { ...this.globalSettings };
  }

  public setEmergencyStop(enabled: boolean): void {
    this.globalSettings.emergencyStop = enabled;
    this.globalSettings.updatedAt = new Date().toISOString();
    this.saveState();
  }

  public setLabelThreshold(labelKey: string, threshold: number): LabelAutonomyState {
    const state = this.getLabelState(labelKey);
    state.requiredThreshold = Math.max(1, threshold);
    if (state.unchangedStreak >= state.requiredThreshold && !state.disabledByUser) {
      state.autonomyEnabled = true;
    } else {
      state.autonomyEnabled = false;
    }
    state.updatedAt = new Date().toISOString();
    this.labelStateMap.set(labelKey, state);
    this.saveState();
    return { ...state };
  }

  public setLabelDisabled(labelKey: string, disabled: boolean): LabelAutonomyState {
    const state = this.getLabelState(labelKey);
    state.disabledByUser = disabled;
    if (disabled) {
      state.autonomyEnabled = false;
    } else if (state.unchangedStreak >= state.requiredThreshold) {
      state.autonomyEnabled = true;
    }
    state.updatedAt = new Date().toISOString();
    this.labelStateMap.set(labelKey, state);
    this.saveState();
    return { ...state };
  }

  /**
   * Autonomy gating rule:
   * 1. Emergency stop disables ALL auto-sending immediately.
   * 2. Must be strictly LOW risk.
   * 3. Checks label-based autonomy if labelKey provided:
   *    - Must not be disabledByUser
   *    - Must meet label threshold X
   *    - Requires reliable knowledge evidence & active Gmail if required
   * 4. Falls back to kindKey (20-approval) for legacy tests.
   */
  public canAutoSend(
    kind: KindTuple,
    labelKey?: string,
    options?: { isGmailConnected?: boolean; evidenceScore?: number; hasEvidence?: boolean }
  ): boolean {
    if (this.globalSettings.emergencyStop) {
      return false;
    }

    if (kind.riskLevel !== RiskLevel.LOW) {
      return false;
    }

    // Gmail connection guard
    if (this.globalSettings.requireGmailConnection && options?.isGmailConnected === false) {
      return false;
    }

    // Evidence reliability guard
    if (options?.hasEvidence === false) {
      return false;
    }
    if (options?.evidenceScore !== undefined && options.evidenceScore < this.globalSettings.minEvidenceScore) {
      return false;
    }

    // If labelKey is supplied, evaluate independent label streak
    if (labelKey) {
      const labelState = this.getLabelState(labelKey);
      if (labelState.disabledByUser) {
        return false;
      }
      return labelState.autonomyEnabled && labelState.unchangedStreak >= labelState.requiredThreshold;
    }

    // Kind-level fallback (for legacy tests)
    if (kind.productArea === ProductArea.UNKNOWN) {
      return false;
    }
    const state = this.getState(kind.key);
    return state.autonomyEnabled && state.unchangedStreak >= 20;
  }

  /**
   * Records a HUMAN review action.
   */
  public recordHumanReview(review: HumanReviewRecord): AutonomyState {
    const state = this.getState(review.kindKey);
    state.totalDrafts += 1;
    state.updatedAt = new Date().toISOString();

    const parts = review.kindKey.split(":");
    const riskLevel = parts[1];
    const productArea = parts[2];
    const isEligibleForAutonomy = riskLevel === RiskLevel.LOW && productArea !== ProductArea.UNKNOWN;

    if (review.action === "APPROVE" && review.wasUnchanged) {
      state.unchangedStreak += 1;
      state.totalSentWithoutChanges += 1;

      // Autonomy only enables if strictly LOW risk and product area is NOT UNKNOWN (legacy: 20 approvals)
      if (state.unchangedStreak >= 20 && isEligibleForAutonomy) {
        state.autonomyEnabled = true;
        state.lastFailureReason = undefined;
      } else {
        state.autonomyEnabled = false;
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

    // Update label streak independently if labelKey is present
    if (review.labelKey) {
      const labelState = this.getLabelState(review.labelKey);
      labelState.totalDrafts += 1;
      labelState.updatedAt = new Date().toISOString();

      if (review.action === "APPROVE" && review.wasUnchanged) {
        labelState.unchangedStreak += 1;
        labelState.totalSentWithoutChanges += 1;

        if (labelState.unchangedStreak >= labelState.requiredThreshold && !labelState.disabledByUser) {
          labelState.autonomyEnabled = true;
          labelState.lastFailureReason = undefined;
        }
      } else {
        labelState.unchangedStreak = 0;
        labelState.autonomyEnabled = false;
        labelState.lastFailureReason =
          review.action === "REJECT"
            ? `Human rejected draft (${review.notes || "Quality rejection"})`
            : `Human edited draft before sending (${review.diffSummary || "Modified text"})`;
      }
      this.labelStateMap.set(review.labelKey, labelState);
    }

    this.saveState();
    return { ...state };
  }

  public recordReview(review: HumanReviewRecord): AutonomyState {
    return this.recordHumanReview(review);
  }

  /**
   * Records an AUTOMATIC delivery.
   * An automatic send NEVER counts as a human approval and does NOT increase unchanged streak.
   */
  public recordAutoDelivery(delivery: AutomaticDeliveryRecord): AutonomyState {
    const state = this.getState(delivery.kindKey);
    state.totalDrafts += 1;
    state.totalSentWithoutChanges += 1;
    // Streak is intentionally NOT incremented
    state.updatedAt = new Date().toISOString();
    this.stateMap.set(delivery.kindKey, state);

    if (delivery.labelKey) {
      const labelState = this.getLabelState(delivery.labelKey);
      labelState.totalDrafts += 1;
      labelState.totalSentWithoutChanges += 1;
      // Label streak is NOT incremented
      labelState.updatedAt = new Date().toISOString();
      this.labelStateMap.set(delivery.labelKey, labelState);
    }

    this.saveState();
    return { ...state };
  }

  /**
   * Explicit quality audit revocation pathway.
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

    // Also check if kindKey matches any labelKey
    if (this.labelStateMap.has(kindKey)) {
      const lState = this.labelStateMap.get(kindKey)!;
      lState.autonomyEnabled = false;
      lState.unchangedStreak = 0;
      lState.lastFailureReason = reason;
      lState.updatedAt = new Date().toISOString();
      this.labelStateMap.set(kindKey, lState);
    }

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

    try {
      if (fs.existsSync(this.labelStateFilePath)) {
        const raw = fs.readFileSync(this.labelStateFilePath, "utf-8");
        const data = JSON.parse(raw);
        if (Array.isArray(data)) {
          for (const item of data) {
            if (item.labelKey) {
              this.labelStateMap.set(item.labelKey, item);
            }
          }
        }
      }
    } catch {
      // Fresh in-memory state
    }

    try {
      if (fs.existsSync(this.settingsFilePath)) {
        const raw = fs.readFileSync(this.settingsFilePath, "utf-8");
        const data = JSON.parse(raw);
        if (data && typeof data.defaultThreshold === "number") {
          this.globalSettings = { ...this.globalSettings, ...data };
        }
      }
    } catch {
      // Fresh in-memory settings
    }
  }

  public saveState(): void {
    try {
      const dir = path.dirname(this.stateFilePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(this.stateFilePath, JSON.stringify(Array.from(this.stateMap.values()), null, 2), "utf-8");
      fs.writeFileSync(this.labelStateFilePath, JSON.stringify(Array.from(this.labelStateMap.values()), null, 2), "utf-8");
      fs.writeFileSync(this.settingsFilePath, JSON.stringify(this.globalSettings, null, 2), "utf-8");
    } catch (err) {
      console.error("Failed to persist autonomy state:", err);
    }
  }

  public resetAll(): void {
    this.stateMap.clear();
    this.labelStateMap.clear();
    this.saveState();
  }
}
