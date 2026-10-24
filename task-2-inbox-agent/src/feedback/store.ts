import fs from "fs";
import path from "path";
import { HumanReviewRecord } from "../types/index.js";

export class FeedbackStore {
  private records: HumanReviewRecord[] = [];
  private readonly filePath: string;

  constructor(filePath?: string) {
    this.filePath = filePath || path.join(process.cwd(), "data", "feedback_store.json");
    this.load();
  }

  public saveReviewRecord(record: HumanReviewRecord): void {
    this.records.push(record);
    this.persist();
  }

  public getHistory(key?: string): HumanReviewRecord[] {
    if (!key) {
      return [...this.records];
    }
    return this.records.filter((r) => r.kindKey === key || r.labelKey === key);
  }

  public getApprovedExemplars(key: string, limit: number = 3): HumanReviewRecord[] {
    return this.records
      .filter((r) => (r.kindKey === key || r.labelKey === key) && (r.action === "APPROVE" || r.wasUnchanged))
      .slice(-limit);
  }

  public getEditedCorrections(key: string, limit: number = 3): HumanReviewRecord[] {
    return this.records
      .filter((r) => (r.kindKey === key || r.labelKey === key) && r.action === "EDIT" && !r.wasUnchanged)
      .slice(-limit);
  }

  /**
   * Retrieves reviewed corrections for a setting type/label that were approved/edited
   * within the past N minutes (default 5 minutes) for immediate few-shot guidance.
   */
  public getRecentCorrections(key: string, withinMinutes: number = 5, limit: number = 3): HumanReviewRecord[] {
    const cutoff = Date.now() - withinMinutes * 60 * 1000;
    return this.records
      .filter((r) => {
        const matchesKey = r.kindKey === key || r.labelKey === key;
        if (!matchesKey) return false;
        const reviewTime = new Date(r.reviewedAt).getTime();
        return reviewTime >= cutoff;
      })
      .slice(-limit);
  }

  public computeMetrics(key?: string) {
    const list = key
      ? this.records.filter((r) => r.kindKey === key || r.labelKey === key)
      : this.records;
    const total = list.length;
    if (total === 0) {
      return {
        totalReviews: 0,
        unchangedCount: 0,
        editCount: 0,
        rejectCount: 0,
        unchangedRate: 0,
        editRate: 0,
        rejectRate: 0
      };
    }
    const unchangedCount = list.filter((r) => r.wasUnchanged).length;
    const editCount = list.filter((r) => r.action === "EDIT").length;
    const rejectCount = list.filter((r) => r.action === "REJECT").length;

    return {
      totalReviews: total,
      unchangedCount,
      editCount,
      rejectCount,
      unchangedRate: Number((unchangedCount / total).toFixed(4)),
      editRate: Number((editCount / total).toFixed(4)),
      rejectRate: Number((rejectCount / total).toFixed(4))
    };
  }

  private load(): void {
    try {
      if (fs.existsSync(this.filePath)) {
        const raw = fs.readFileSync(this.filePath, "utf-8");
        this.records = JSON.parse(raw);
      }
    } catch {
      this.records = [];
    }
  }

  private persist(): void {
    try {
      const dir = path.dirname(this.filePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(this.filePath, JSON.stringify(this.records, null, 2), "utf-8");
    } catch (err) {
      console.error("Failed to persist feedback records:", err);
    }
  }

  public clear(): void {
    this.records = [];
    this.persist();
  }
}
