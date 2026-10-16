import {
  CustomerEmail,
  ProcessingResult,
  HumanReviewRecord,
  ReviewAction,
  DraftReply
} from "./types/index.js";
import { EmailClassifier } from "./classification/classifier.js";
import { Task1KnowledgeClient } from "./knowledge/task1_client.js";
import { DraftGenerator } from "./drafting/generator.js";
import { AutonomyEngine } from "./autonomy/engine.js";
import { FeedbackStore } from "./feedback/store.js";

export class InboxService {
  public readonly classifier: EmailClassifier;
  public readonly knowledgeClient: Task1KnowledgeClient;
  public readonly draftGenerator: DraftGenerator;
  public readonly autonomyEngine: AutonomyEngine;
  public readonly feedbackStore: FeedbackStore;

  private pendingDrafts: Map<string, { email: CustomerEmail; draft: DraftReply; kindKey: string }> = new Map();

  constructor(options?: {
    knowledgeClient?: Task1KnowledgeClient;
    autonomyEngine?: AutonomyEngine;
    feedbackStore?: FeedbackStore;
  }) {
    this.classifier = new EmailClassifier();
    this.knowledgeClient = options?.knowledgeClient || new Task1KnowledgeClient();
    this.feedbackStore = options?.feedbackStore || new FeedbackStore();
    this.draftGenerator = new DraftGenerator({ feedbackStore: this.feedbackStore });
    this.autonomyEngine = options?.autonomyEngine || new AutonomyEngine();
  }

  public async processEmail(
    email: CustomerEmail,
    version: "v1_baseline" | "v2_feedback_enhanced" = "v1_baseline"
  ): Promise<ProcessingResult> {
    // 1. Classification
    const classification = this.classifier.classify(email);
    const kind = classification.kind;

    // 2. Query Task 1 Knowledge Brain (only if not an injection / high-risk security issue)
    let knowledgeResponse;
    if (!classification.riskFlags.includes("PROMPT_INJECTION_DETECTED")) {
      const kResult = await this.knowledgeClient.askKnowledgeBrain(
        `${email.subject}. ${email.body}`,
        kind.productArea !== "UNKNOWN" ? kind.productArea : undefined
      );
      knowledgeResponse = kResult.response;
      if (kResult.needsHumanEscalation) {
        classification.requiresHumanReview = true;
      }
    }

    // 3. Generate Draft
    const draft = await this.draftGenerator.generateDraft(email, classification, knowledgeResponse, version);

    // 4. Autonomy Policy Gating
    const canAuto = this.autonomyEngine.canAutoSend(kind) && draft.autoSendEligible;
    const currentAutonomyState = this.autonomyEngine.getState(kind.key);

    let routedTo: "AUTO_SENT" | "HUMAN_REVIEW_QUEUE" = "HUMAN_REVIEW_QUEUE";
    let finalSentReply: string | undefined;

    if (canAuto) {
      routedTo = "AUTO_SENT";
      finalSentReply = draft.body;

      // Record autonomous delivery as an unchanged auto-approved event
      const autoRecord: HumanReviewRecord = {
        id: `auto_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        emailId: email.id,
        draftId: draft.id,
        kindKey: kind.key,
        action: "APPROVE",
        originalDraft: draft.body,
        finalSentReply: draft.body,
        wasUnchanged: true,
        reviewerId: "system_autonomous_agent",
        reviewedAt: new Date().toISOString(),
        notes: "Autonomous send executed (streak >= 20, LOW risk)"
      };
      this.feedbackStore.saveReviewRecord(autoRecord);
      this.autonomyEngine.recordReview(autoRecord);
    } else {
      // Retain in pending queue for human review
      this.pendingDrafts.set(email.id, { email, draft, kindKey: kind.key });
    }

    return {
      email,
      classification,
      knowledgeResponse,
      draft,
      routedTo,
      autonomyState: currentAutonomyState,
      finalSentReply
    };
  }

  public reviewDraft(
    emailId: string,
    action: ReviewAction,
    finalReply?: string,
    reviewerId: string = "human_operator_1",
    notes?: string
  ): HumanReviewRecord {
    const pending = this.pendingDrafts.get(emailId);
    if (!pending) {
      throw new Error(`No pending draft found for email ID: ${emailId}`);
    }

    const { draft, kindKey } = pending;
    const sentText = action === "APPROVE" ? draft.body : (finalReply || draft.body);

    const wasUnchanged = action === "APPROVE" && this.autonomyEngine.isUnchanged(draft.body, sentText);

    const record: HumanReviewRecord = {
      id: `rev_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      emailId,
      draftId: draft.id,
      kindKey,
      action,
      originalDraft: draft.body,
      finalSentReply: sentText,
      wasUnchanged,
      diffSummary: wasUnchanged ? "Zero changes" : `Modified by ${reviewerId}`,
      reviewerId,
      reviewedAt: new Date().toISOString(),
      notes
    };

    this.feedbackStore.saveReviewRecord(record);
    this.autonomyEngine.recordReview(record);
    this.pendingDrafts.delete(emailId);

    return record;
  }

  public getPendingDrafts(): Array<{ email: CustomerEmail; draft: DraftReply; kindKey: string }> {
    return Array.from(this.pendingDrafts.values());
  }
}
