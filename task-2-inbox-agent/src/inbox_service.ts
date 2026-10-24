import {
  CustomerEmail,
  ProcessingResult,
  HumanReviewRecord,
  ReviewAction,
  InteractionRecord,
  AutomaticDeliveryRecord
} from "./types/index.js";
import { CustomerEmailSchema, ReviewSubmissionSchema } from "./validation/schemas.js";
import { EmailClassifier } from "./classification/classifier.js";
import { Task1KnowledgeClient } from "./knowledge/task1_client.js";
import { DraftGenerator } from "./drafting/generator.js";
import { AutonomyEngine } from "./autonomy/engine.js";
import { FeedbackStore } from "./feedback/store.js";
import { InteractionStore } from "./storage/interaction_store.js";
import { GmailClient } from "./gmail/client.js";

export interface ReviewSubmission {
  action: ReviewAction;
  reviewerId: string;
  finalReply?: string;
  notes?: string;
  sendViaGmail?: boolean;
}

export class InboxService {
  public readonly classifier: EmailClassifier;
  public readonly knowledgeClient: Task1KnowledgeClient;
  public readonly draftGenerator: DraftGenerator;
  public readonly autonomyEngine: AutonomyEngine;
  public readonly feedbackStore: FeedbackStore;
  public readonly interactionStore: InteractionStore;
  public readonly gmailClient: GmailClient;

  constructor(options?: {
    knowledgeClient?: Task1KnowledgeClient;
    autonomyEngine?: AutonomyEngine;
    feedbackStore?: FeedbackStore;
    interactionStore?: InteractionStore;
    allowDeterministicAutoSend?: boolean;
    draftGenerator?: DraftGenerator;
    gmailClient?: GmailClient;
  }) {
    this.classifier = new EmailClassifier();
    this.knowledgeClient = options?.knowledgeClient || new Task1KnowledgeClient();
    this.feedbackStore = options?.feedbackStore || new FeedbackStore();
    this.interactionStore = options?.interactionStore || new InteractionStore();
    this.draftGenerator = options?.draftGenerator || new DraftGenerator({ feedbackStore: this.feedbackStore, allowDeterministicAutoSend: options?.allowDeterministicAutoSend });
    this.autonomyEngine = options?.autonomyEngine || new AutonomyEngine();
    this.gmailClient = options?.gmailClient || new GmailClient();
  }

  public async processEmail(
    rawEmail: unknown,
    version: "v1_baseline" | "v2_feedback_enhanced" = "v1_baseline"
  ): Promise<ProcessingResult> {
    // 1. Runtime validation
    const parsed = CustomerEmailSchema.safeParse(rawEmail);
    if (!parsed.success) {
      throw new Error(`Invalid email payload: ${parsed.error.errors.map((e) => e.message).join(", ")}`);
    }
    const email: CustomerEmail = parsed.data;

    // 2. Classification
    const classification = this.classifier.classify(email);
    const kind = classification.kind;

    // 3. Query Task 1 Knowledge Brain (bypassed if prompt injection is detected)
    let knowledgeResponse;
    let task1Success = false;
    let task1Available = false;
    let fallbackReason: string | undefined;

    if (!classification.riskFlags.includes("PROMPT_INJECTION_DETECTED")) {
      const kResult = await this.knowledgeClient.askKnowledgeBrain(
        `${email.subject}. ${email.body}`,
        undefined
      );
      knowledgeResponse = kResult.response;
      task1Success = kResult.success;
      task1Available = kResult.isAvailable;
      fallbackReason = kResult.fallbackReason;

      if (kResult.needsHumanEscalation) {
        classification.requiresHumanReview = true;
      }
    } else {
      classification.requiresHumanReview = true;
      fallbackReason = "Security prompt injection detected; knowledge query bypassed";
    }

    // 4. Generate Draft
    const draft = await this.draftGenerator.generateDraft(email, classification, knowledgeResponse, version);

    // 5. Autonomy Policy Gating
    const canAuto =
      this.autonomyEngine.canAutoSend(kind, classification.labelKey, {
        isGmailConnected: this.gmailClient.isConnected(),
        evidenceScore: knowledgeResponse?.evidence_score,
        hasEvidence: Boolean(knowledgeResponse?.is_known && knowledgeResponse?.evidence_status !== "NONE")
      }) && draft.autoSendEligible;

    const currentAutonomyState = this.autonomyEngine.getState(kind.key);
    const currentLabelState = this.autonomyEngine.getLabelState(classification.labelKey);

    let routedTo: "AUTO_SENT" | "HUMAN_REVIEW_QUEUE" = "HUMAN_REVIEW_QUEUE";
    let finalSentReply: string | undefined;
    let gmailMessageId: string | undefined;

    const interactionId = draft.id;
    const now = new Date().toISOString();

    if (canAuto) {
      routedTo = "AUTO_SENT";
      finalSentReply = draft.body;

      // Send via Gmail if connected
      if (this.gmailClient.isConnected()) {
        try {
          const sendRes = await this.gmailClient.sendEmail({
            to: email.senderEmail,
            subject: draft.subject,
            body: draft.body,
            inReplyTo: email.id
          });
          gmailMessageId = sendRes.messageId;
        } catch (sendErr) {
          console.warn("[AUTO-SEND GMAIL] API send failed, routing to review queue:", sendErr);
          routedTo = "HUMAN_REVIEW_QUEUE";
          finalSentReply = undefined;
        }
      }

      if (routedTo === "AUTO_SENT") {
        // CRITICAL: An automatic send is recorded into auto-delivery store.
        // It NEVER creates a human review record and NEVER increments unchanged streak.
        const deliveryRecord: AutomaticDeliveryRecord = {
          id: `auto_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
          interactionId,
          emailId: email.id,
          draftId: draft.id,
          kindKey: kind.key,
          labelKey: classification.labelKey,
          sentReply: draft.body,
          sentAt: now,
          promptVersion: version,
          gmailMessageId
        };

        this.interactionStore.recordAutoDelivery(deliveryRecord);
        this.autonomyEngine.recordAutoDelivery(deliveryRecord);
      }
    }

    // 6. Persist complete interaction record
    const interaction: InteractionRecord = {
      id: interactionId,
      email,
      classification,
      task1Status: {
        success: task1Success,
        isAvailable: task1Available,
        evidenceScore: knowledgeResponse?.evidence_score ?? 0,
        evidenceStatus: knowledgeResponse?.evidence_status ?? "NONE",
        needsHumanReview: classification.requiresHumanReview,
        fallbackReason
      },
      draft,
      promptVersion: version,
      routingDecision: routedTo,
      status: routedTo === "AUTO_SENT" ? "AUTO_SENT" : "PENDING_REVIEW",
      finalSentReply,
      gmailMessageId,
      createdAt: now,
      updatedAt: now
    };

    this.interactionStore.saveInteraction(interaction);

    return {
      email,
      classification,
      knowledgeResponse,
      draft,
      routedTo,
      autonomyState: currentAutonomyState,
      labelAutonomyState: currentLabelState,
      interactionId,
      finalSentReply,
      gmailMessageId
    };
  }

  public getPendingReviews(): InteractionRecord[] {
    return this.interactionStore.getPendingInteractions();
  }

  public getInteraction(id: string): InteractionRecord | undefined {
    return this.interactionStore.getInteraction(id);
  }

  public submitReview(
    interactionId: string,
    rawSubmission: unknown
  ): { interaction: InteractionRecord; reviewRecord: HumanReviewRecord } {
    // 1. Validate submission
    const parseResult = ReviewSubmissionSchema.safeParse(rawSubmission);
    if (!parseResult.success) {
      throw new Error(`Invalid review submission: ${parseResult.error.errors.map((e) => e.message).join(", ")}`);
    }
    const submission: ReviewSubmission = parseResult.data;

    // 2. Fetch pending interaction
    const interaction = this.interactionStore.getInteraction(interactionId);
    if (!interaction) {
      throw new Error(`Interaction '${interactionId}' not found`);
    }

    if (interaction.status !== "PENDING_REVIEW") {
      throw new Error(`Interaction '${interactionId}' is already resolved (${interaction.status})`);
    }

    const now = new Date().toISOString();
    let finalSentReply: string | undefined;
    let wasUnchanged = false;
    let diffSummary: string | undefined;

    if (submission.action === "APPROVE") {
      finalSentReply = interaction.draft.body;
      wasUnchanged = true;
    } else if (submission.action === "EDIT") {
      if (!submission.finalReply || submission.finalReply.trim().length === 0) {
        throw new Error("EDIT action requires a non-empty finalReply");
      }
      if (this.autonomyEngine.isUnchanged(interaction.draft.body, submission.finalReply)) {
        throw new Error("EDIT requires finalReply to differ from draft. For unchanged drafts, select APPROVE.");
      }
      finalSentReply = submission.finalReply;
      wasUnchanged = false;
      diffSummary = `Modified length ${interaction.draft.body.length} -> ${submission.finalReply.length}`;
    } else if (submission.action === "REJECT") {
      // CRITICAL Requirement 12: REJECT must not populate finalSentReply
      finalSentReply = undefined;
      wasUnchanged = false;
      diffSummary = submission.notes || "Draft rejected by human reviewer";
    }

    // 3. Create HumanReviewRecord
    const reviewRecord: HumanReviewRecord = {
      id: `rev_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
      emailId: interaction.email.id,
      draftId: interaction.draft.id,
      kindKey: interaction.classification.kind.key,
      parentSettingType: interaction.classification.parentSettingType,
      specificLabel: interaction.classification.specificLabel,
      labelKey: interaction.classification.labelKey,
      action: submission.action,
      originalDraft: interaction.draft.body,
      finalSentReply,
      wasUnchanged,
      diffSummary,
      reviewerId: submission.reviewerId,
      reviewedAt: now,
      notes: submission.notes
    };

    // 4. Update Autonomy Engine with human review action (updates both kind and label streaks)
    this.autonomyEngine.recordHumanReview(reviewRecord);

    // 5. Update Feedback Store for continuous learning
    this.feedbackStore.saveReviewRecord(reviewRecord);

    // 6. Update Interaction Store
    const newStatus =
      submission.action === "APPROVE" ? "APPROVED" : submission.action === "EDIT" ? "EDITED" : "REJECTED";

    this.interactionStore.updateReviewStatus(
      interactionId,
      newStatus,
      submission.action,
      finalSentReply,
      submission.reviewerId,
      submission.notes
    );

    interaction.status = newStatus;
    interaction.reviewAction = submission.action;
    interaction.finalSentReply = finalSentReply;
    interaction.reviewerId = submission.reviewerId;
    interaction.reviewedAt = now;
    interaction.reviewNotes = submission.notes;

    return { interaction, reviewRecord };
  }

  public async sendApprovedEmailViaGmail(
    interactionId: string
  ): Promise<{ success: boolean; messageId: string; threadId: string }> {
    const interaction = this.interactionStore.getInteraction(interactionId);
    if (!interaction) {
      throw new Error(`Interaction '${interactionId}' not found`);
    }
    if (!interaction.finalSentReply) {
      throw new Error(`Interaction '${interactionId}' has no approved reply to send`);
    }
    if (!this.gmailClient.isConnected()) {
      throw new Error("Gmail is not connected. Connect via OAuth before sending.");
    }

    const sendRes = await this.gmailClient.sendEmail({
      to: interaction.email.senderEmail,
      subject: interaction.draft.subject,
      body: interaction.finalSentReply,
      inReplyTo: interaction.email.id
    });

    interaction.gmailMessageId = sendRes.messageId;
    this.interactionStore.saveInteraction(interaction);
    return sendRes;
  }

  /**
   * Fetches unread messages from connected Gmail account and processes each exactly once.
   */
  public async syncGmail(maxCount: number = 20): Promise<{ fetched: number; processed: number; items: ProcessingResult[] }> {
    if (!this.gmailClient.isConnected()) {
      return { fetched: 0, processed: 0, items: [] };
    }

    const list = await this.gmailClient.listInboxMessages(maxCount);
    const results: ProcessingResult[] = [];

    for (const item of list) {
      if (this.gmailClient.isMessageProcessed(item.id)) {
        continue;
      }

      try {
        const full = await this.gmailClient.getMessage(item.id);
        const email: CustomerEmail = {
          id: full.id,
          senderEmail: full.sender.includes("<") ? full.sender.split("<")[1].replace(">", "").trim() : full.sender,
          senderName: full.sender.includes("<") ? full.sender.split("<")[0].replace(/"/g, "").trim() : undefined,
          subject: full.subject,
          body: full.bodyText,
          receivedAt: full.date
        };

        const res = await this.processEmail(email, "v2_feedback_enhanced");
        this.gmailClient.markMessageProcessed(item.id);
        results.push(res);
      } catch (err) {
        console.warn(`Failed to process Gmail message ${item.id}:`, err);
      }
    }

    return {
      fetched: list.length,
      processed: results.length,
      items: results
    };
  }

  public revokeAutonomy(kindKey: string, reason: string, revokedBy?: string) {
    return this.autonomyEngine.revokeAutonomy(kindKey, reason, revokedBy);
  }
}
