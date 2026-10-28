import fs from "fs";
import path from "path";
import { InteractionRecord, AutomaticDeliveryRecord, InteractionStatus } from "../types/index.js";

export interface InteractionStoreOptions {
  storagePath?: string;
  autoDeliveryPath?: string;
}

export class InteractionStore {
  private readonly storagePath: string;
  private readonly autoDeliveryPath: string;
  private interactions: Map<string, InteractionRecord> = new Map();
  private autoDeliveries: AutomaticDeliveryRecord[] = [];

  constructor(options: InteractionStoreOptions = {}) {
    this.storagePath = options.storagePath || path.resolve("data", "interactions.json");
    this.autoDeliveryPath = options.autoDeliveryPath || path.resolve("data", "auto_deliveries.json");
    this.load();
  }

  public saveInteraction(record: InteractionRecord): void {
    this.interactions.set(record.id, record);
    this.persistInteractions();
  }

  public getInteraction(id: string): InteractionRecord | undefined {
    return this.interactions.get(id);
  }

  public getPendingInteractions(): InteractionRecord[] {
    return Array.from(this.interactions.values())
      .filter((rec) => rec.status === "PENDING_REVIEW")
      .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  }

  public updateReviewStatus(
    id: string,
    status: InteractionStatus,
    reviewAction?: "APPROVE" | "EDIT" | "REJECT",
    finalSentReply?: string,
    reviewerId?: string,
    notes?: string
  ): InteractionRecord | undefined {
    const existing = this.interactions.get(id);
    if (!existing) return undefined;

    existing.status = status;
    existing.reviewAction = reviewAction;
    existing.finalSentReply = finalSentReply;
    existing.reviewerId = reviewerId;
    existing.reviewNotes = notes;
    existing.reviewedAt = new Date().toISOString();
    existing.updatedAt = new Date().toISOString();

    this.persistInteractions();
    return existing;
  }

  public moveToFolder(id: string, folder: import("../types/index.js").EmailFolder): InteractionRecord | undefined {
    const existing = this.interactions.get(id);
    if (!existing) return undefined;
    existing.folder = folder;
    existing.updatedAt = new Date().toISOString();
    this.persistInteractions();
    return existing;
  }

  public deleteInteraction(id: string): boolean {
    const deleted = this.interactions.delete(id);
    if (deleted) {
      this.persistInteractions();
    }
    return deleted;
  }

  public recordAutoDelivery(record: AutomaticDeliveryRecord): void {
    this.autoDeliveries.push(record);
    this.persistAutoDeliveries();
  }

  public getAutoDeliveries(): AutomaticDeliveryRecord[] {
    return [...this.autoDeliveries];
  }

  public getAllInteractions(): InteractionRecord[] {
    return Array.from(this.interactions.values());
  }

  private load(): void {
    try {
      if (fs.existsSync(this.storagePath)) {
        const raw = fs.readFileSync(this.storagePath, "utf8");
        const list: InteractionRecord[] = JSON.parse(raw);
        this.interactions.clear();
        for (const item of list) {
          this.interactions.set(item.id, item);
        }
      }
    } catch (err) {
      console.warn("Failed to load interactions store from disk, starting fresh:", err);
    }

    try {
      if (fs.existsSync(this.autoDeliveryPath)) {
        const raw = fs.readFileSync(this.autoDeliveryPath, "utf8");
        this.autoDeliveries = JSON.parse(raw);
      }
    } catch (err) {
      console.warn("Failed to load auto deliveries store from disk, starting fresh:", err);
    }
  }

  private persistInteractions(): void {
    try {
      const dir = path.dirname(this.storagePath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(this.storagePath, JSON.stringify(Array.from(this.interactions.values()), null, 2), "utf8");
    } catch (err) {
      console.error("Failed to persist interactions store:", err);
    }
  }

  private persistAutoDeliveries(): void {
    try {
      const dir = path.dirname(this.autoDeliveryPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
      fs.writeFileSync(this.autoDeliveryPath, JSON.stringify(this.autoDeliveries, null, 2), "utf8");
    } catch (err) {
      console.error("Failed to persist auto deliveries store:", err);
    }
  }
}
