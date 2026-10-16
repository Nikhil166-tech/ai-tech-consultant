import {
  CustomerEmail,
  EmailClassification,
  Task1AskResponse,
  DraftReply,
  Task1Citation
} from "../types/index.js";
import { FeedbackStore } from "../feedback/store.js";

export interface DraftGeneratorOptions {
  apiKey?: string;
  model?: string;
  feedbackStore?: FeedbackStore;
}

export class DraftGenerator {
  private readonly apiKey?: string;
  private readonly model: string;
  private readonly feedbackStore: FeedbackStore;

  constructor(options: DraftGeneratorOptions = {}) {
    this.apiKey = options.apiKey || process.env.ANTHROPIC_API_KEY;
    this.model = options.model || process.env.ANTHROPIC_MODEL_TEXT || "claude-haiku-5-5";
    this.feedbackStore = options.feedbackStore || new FeedbackStore();
  }

  public async generateDraft(
    email: CustomerEmail,
    classification: EmailClassification,
    knowledge?: Task1AskResponse,
    version: "v1_baseline" | "v2_feedback_enhanced" = "v1_baseline"
  ): Promise<DraftReply> {
    const draftId = `draft_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const isEscalation = classification.requiresHumanReview || !knowledge || !knowledge.is_known || knowledge.needs_human_review;

    // Check if auto-send is blocked
    let autoSendEligible = !isEscalation && classification.kind.riskLevel === "LOW";
    let blockReason: string | undefined;

    if (isEscalation) {
      autoSendEligible = false;
      blockReason = classification.riskFlags.length > 0
        ? `High-risk flags detected: [${classification.riskFlags.join(", ")}]`
        : !knowledge?.is_known
        ? "Insufficient documentation evidence in Knowledge Brain"
        : "Human specialist review flagged as required";
    }

    // Try Claude API if key present
    let bodyText = "";
    if (this.apiKey) {
      try {
        bodyText = await this.synthesizeWithClaude(email, classification, knowledge, version);
      } catch (err) {
        console.warn("Claude API synthesis failed; using deterministic template synthesis:", err);
      }
    }

    if (!bodyText) {
      bodyText = this.synthesizeDeterministic(email, classification, knowledge, version);
    }

    const citations: Task1Citation[] = knowledge?.citations || [];

    return {
      id: draftId,
      emailId: email.id,
      subject: email.subject.startsWith("Re:") ? email.subject : `Re: ${email.subject}`,
      body: bodyText,
      generatedAt: new Date().toISOString(),
      promptVersion: version,
      knowledgeEvidenceScore: knowledge?.evidence_score ?? 0.0,
      citations,
      autoSendEligible,
      blockReason
    };
  }

  private synthesizeDeterministic(
    email: CustomerEmail,
    classification: EmailClassification,
    knowledge: Task1AskResponse | undefined,
    version: "v1_baseline" | "v2_feedback_enhanced"
  ): string {
    const sender = email.senderName || "there";
    const header = `Hi ${sender},\n\nThank you for reaching out to Brilliant Directories Support.`;
    const signoff = `\n\nBest regards,\nAI Tech Consultant Team\nBrilliant Directories`;

    // 1. High Risk / Escalation Responses
    if (classification.riskFlags.includes("ACCOUNT_CANCELLATION")) {
      return (
        `${header}\n\n` +
        `We have received your cancellation request. Because account cancellation and subscription adjustments ` +
        `require account ownership confirmation and billing audit, our retention and cancellation specialist team ` +
        `has been assigned to your ticket. A specialist will review your account details and follow up promptly.` +
        signoff
      );
    }

    if (classification.riskFlags.includes("FINANCIAL_DISPUTE_OR_REFUND")) {
      return (
        `${header}\n\n` +
        `We have received your billing inquiry regarding account charges. Because financial reviews and refund requests ` +
        `require strict account verification and manual audit, our billing department has been assigned to your ticket. ` +
        `A billing specialist will review your transaction history and follow up with you directly within 1 business day.` +
        signoff
      );
    }

    if (classification.riskFlags.includes("LEGAL_OR_COMPLIANCE_RISK")) {
      return (
        `${header}\n\n` +
        `We acknowledge receipt of your communication. Your inquiry has been routed to our compliance and executive ` +
        `specialist team for formal review. A team representative will contact you directly.` +
        signoff
      );
    }

    if (classification.riskFlags.includes("ACCOUNT_SECURITY_COMPROMISE") || classification.riskFlags.includes("PROMPT_INJECTION_DETECTED")) {
      return (
        `${header}\n\n` +
        `We have received your security request. For your protection, sensitive account access inquiries ` +
        `undergo verified identity checks and strict verification. A senior security engineer will review this request shortly.` +
        signoff
      );
    }

    // 2. Insufficient Verified Knowledge
    if (!knowledge || !knowledge.is_known || knowledge.evidence_status === "INSUFFICIENT" || knowledge.evidence_status === "NONE") {
      return (
        `${header}\n\n` +
        `Thank you for asking about '${email.subject}'. We do not have sufficient verified documentation ` +
        `in our Solution Center to immediately answer your exact scenario. We have routed this question to our ` +
        `product engineering team for verified confirmation, and will follow up as soon as they clarify the procedure.` +
        signoff
      );
    }

    // 3. Verified Knowledge Brain Resolution
    let answerCore = knowledge.answer.trim();
    if (answerCore.includes("Customer Question:")) {
      answerCore = answerCore.split("Customer Question:")[0].trim();
    }

    let citationsBlock = "";
    if (knowledge.citations && knowledge.citations.length > 0) {
      const topCitation = knowledge.citations[0];
      citationsBlock = `\n\nOfficial Documentation Reference:\n- ${topCitation.title} (${topCitation.section_heading}): ${topCitation.url}`;
    }

    // Version 2 incorporates reviewer few-shot feedback guidance
    let feedbackAddendum = "";
    if (version === "v2_feedback_enhanced") {
      const exemplars = this.feedbackStore.getApprovedExemplars(classification.kind.key, 1);
      if (exemplars.length > 0 && exemplars[0].finalSentReply) {
        feedbackAddendum = "\n\nPlease let us know if you have any questions while testing these settings.";
      }
    }

    return `${header}\n\n${answerCore}${citationsBlock}${feedbackAddendum}${signoff}`;
  }

  private async synthesizeWithClaude(
    email: CustomerEmail,
    classification: EmailClassification,
    knowledge: Task1AskResponse | undefined,
    version: "v1_baseline" | "v2_feedback_enhanced"
  ): Promise<string> {
    const feedbackContext = version === "v2_feedback_enhanced"
      ? this.buildFeedbackContext(classification.kind.key)
      : "";

    const systemPrompt =
      `You are the customer-facing AI Tech Consultant for Brilliant Directories.\n` +
      `Your tone is professional, warm, precise, and concise. Never hallucinate product settings.\n` +
      `Answer strictly based on verified evidence provided from the Knowledge Brain.\n` +
      `${feedbackContext}\n` +
      `Do not include markdown triple backticks.`;

    const userPrompt =
      `Customer Subject: ${email.subject}\n` +
      `Customer Email Body:\n${email.body}\n\n` +
      `Verified Knowledge Base Evidence:\n${knowledge?.answer || "None available"}\n\n` +
      `Draft a direct, helpful customer reply.`;

    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "x-api-key": this.apiKey!,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: 500,
        system: systemPrompt,
        messages: [{ role: "user", content: userPrompt }]
      })
    });

    if (!res.ok) {
      throw new Error(`Claude API error HTTP ${res.status}`);
    }

    const data: any = await res.json();
    return data.content[0].text.trim();
  }

  private buildFeedbackContext(kindKey: string): string {
    const approved = this.feedbackStore.getApprovedExemplars(kindKey, 2);
    const corrections = this.feedbackStore.getEditedCorrections(kindKey, 2);

    let context = "\n[HUMAN REVIEWER FEEDBACK GUIDELINES]:\n";
    if (corrections.length > 0) {
      context += "Past human edits on this exact topic corrected the following:\n";
      corrections.forEach((c, idx) => {
        context += `Correction ${idx + 1}: ${c.diffSummary || "Revised phrasing for precision and clarity."}\n`;
      });
    }
    if (approved.length > 0) {
      context += "Example of human-approved reply:\n" + approved[0].finalSentReply.slice(0, 200) + "...\n";
    }
    return context;
  }
}
