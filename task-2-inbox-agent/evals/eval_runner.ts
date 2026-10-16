import { InboxService } from "../src/inbox_service.js";
import { Task1KnowledgeClient } from "../src/knowledge/task1_client.js";
import { task2EvalCases, Task2EvalCase } from "./task2_eval_suite.js";
import { HumanReviewRecord } from "../src/types/index.js";

/**
 * SYNTHETIC TRAINING FIXTURES:
 * Distinct from the held-out 20 benchmark eval cases.
 * Rule: Any record marked APPROVE + wasUnchanged=true must have normalized-identical original and final text.
 * Any record where text was modified is strictly marked EDIT + wasUnchanged=false.
 */
export const SYNTHETIC_TRAINING_EXEMPLARS: HumanReviewRecord[] = [
  {
    id: "synth_train_01",
    emailId: "train_email_01",
    draftId: "train_draft_01",
    kindKey: "HOW_TO_CONFIGURE:LOW:PAYMENTS_GATEWAYS",
    action: "EDIT",
    originalDraft: "Go to Finance Settings to configure Stripe.",
    finalSentReply: "To configure Stripe, navigate to Finance > Payment Gateways. Enter your keys and test in test mode. Please let us know if you have any questions while testing these settings.",
    wasUnchanged: false,
    diffSummary: "Reviewer added safety reminder to test in test mode and added closing support offer.",
    reviewerId: "synthetic_specialist_alice",
    reviewedAt: new Date(Date.now() - 86400000).toISOString()
  },
  {
    id: "synth_train_02",
    emailId: "train_email_02",
    draftId: "train_draft_02",
    kindKey: "HOW_TO_CONFIGURE:LOW:DOMAINS_DNS",
    action: "EDIT",
    originalDraft: "Set your A record in DNS.",
    finalSentReply: "Navigate to Settings > Domain Manager to view your BD server IP. In your DNS provider, set an A Record pointing to this IP. Please let us know if you have any questions while testing these settings.",
    wasUnchanged: false,
    diffSummary: "Reviewer clarified exact navigation path and added closing support offer.",
    reviewerId: "synthetic_specialist_bob",
    reviewedAt: new Date(Date.now() - 43200000).toISOString()
  },
  {
    id: "synth_train_03",
    emailId: "train_email_03",
    draftId: "train_draft_03",
    kindKey: "HOW_TO_CONFIGURE:LOW:MEMBERSHIP_PLANS",
    action: "EDIT",
    originalDraft: "To manage plans, navigate to Finance > Membership Plans.",
    finalSentReply: "To manage plans, navigate to Finance > Membership Plans. Please let us know if you have any questions while testing these settings.",
    wasUnchanged: false,
    diffSummary: "Reviewer added closing support offer.",
    reviewerId: "synthetic_specialist_alice",
    reviewedAt: new Date(Date.now() - 21600000).toISOString()
  },
  {
    id: "synth_train_04",
    emailId: "train_email_04",
    draftId: "train_draft_04",
    kindKey: "HOW_TO_CONFIGURE:LOW:FORMS_RECAPTCHA",
    action: "APPROVE",
    originalDraft: "To enable Google reCAPTCHA, navigate to Settings > General Settings > Integrations and paste your site key.",
    finalSentReply: "To enable Google reCAPTCHA, navigate to Settings > General Settings > Integrations and paste your site key.",
    wasUnchanged: true,
    reviewerId: "synthetic_specialist_bob",
    reviewedAt: new Date(Date.now() - 10800000).toISOString()
  }
];

interface VersionEvalMetrics {
  version: string;
  totalCases: number;
  intentAccuracy: number;
  riskAccuracy: number;
  areaAccuracy: number;
  routingAccuracy: number;
  contentSafetyPassRate: number;
  contentCompletenessRate: number;
  feedbackIncorporationRate: number;
  averageLatencyMs: number;
}

export async function runTask2Evaluations(): Promise<{ v1: VersionEvalMetrics; v2: VersionEvalMetrics }> {
  console.log("================================================================================");
  console.log("       BUSINESS LABS TASK 2 EVALUATION SUITE: INBOX AGENT BENCHMARK            ");
  console.log("================================================================================");

  const task1Url = process.env.TASK1_API_URL || "http://127.0.0.1:8000";
  const realKnowledgeClient = new Task1KnowledgeClient({ baseUrl: task1Url });

  // Verify real Task 1 Knowledge Brain connectivity (CRITICAL: Zero knowledge duplication)
  try {
    const healthRes = await fetch(`${task1Url}/health`);
    if (!healthRes.ok) {
      throw new Error(`Task 1 returned HTTP ${healthRes.status}`);
    }
    const healthData: any = await healthRes.json();
    console.log(`[Task 1 Integration] Connected to Knowledge Brain at ${task1Url} (${healthData.chunks_count || 0} indexed chunks)`);
  } catch (err: any) {
    console.error(`\n[FATAL] Task 1 Knowledge Brain is not running at ${task1Url}.`);
    console.error("Task 2 strictly requires real Task 1 for integration evaluation per architectural requirements.");
    console.error("Please run Task 1 (py -m app.main) and re-run eval.");
    process.exit(1);
  }

  const allowDeterministic = process.env.ALLOW_DETERMINISTIC_AUTO_SEND === "true" || !process.env.ANTHROPIC_API_KEY;

  // 1. Run Baseline v1 (Zero few-shot exemplars)
  console.log("\n[1/2] Evaluating Baseline Prompt v1 on Held-Out Cases (Zero Few-Shot Exemplars)...");
  const inboxV1 = new InboxService({
    knowledgeClient: realKnowledgeClient,
    allowDeterministicAutoSend: allowDeterministic
  });
  const v1Results = await evaluateVersion(inboxV1, "v1_baseline");

  // 2. Ingest Distinct Synthetic Training Exemplars (Held-out separation)
  console.log("\n[2/2] Ingesting Labeled Synthetic Training Exemplars into FeedbackStore...");
  const inboxV2 = new InboxService({
    knowledgeClient: realKnowledgeClient,
    allowDeterministicAutoSend: allowDeterministic
  });
  for (const exemplar of SYNTHETIC_TRAINING_EXEMPLARS) {
    inboxV2.feedbackStore.saveReviewRecord(exemplar);
  }

  // 3. Run Feedback-Enhanced v2 on the same Held-Out Cases
  console.log("[2/2] Evaluating Feedback-Enhanced Prompt v2 on Held-Out Cases (With Feedback Guidance)...");
  const v2Results = await evaluateVersion(inboxV2, "v2_feedback_enhanced");

  // Output Empirical Results Table (Distinct, honest metrics)
  console.log("\n=========================================================================================================");
  console.log("                               ACTUAL EMPIRICAL TASK 2 EVALUATION RESULTS                                ");
  console.log("=========================================================================================================");
  console.table([
    {
      Version: v1Results.version,
      "Cases": v1Results.totalCases,
      "Intent Acc": `${(v1Results.intentAccuracy * 100).toFixed(1)}%`,
      "Risk Acc": `${(v1Results.riskAccuracy * 100).toFixed(1)}%`,
      "Area Acc": `${(v1Results.areaAccuracy * 100).toFixed(1)}%`,
      "Routing Acc": `${(v1Results.routingAccuracy * 100).toFixed(1)}%`,
      "Safety Pass": `${(v1Results.contentSafetyPassRate * 100).toFixed(1)}%`,
      "Completeness": `${(v1Results.contentCompletenessRate * 100).toFixed(1)}%`,
      "Feedback Incorp": `${(v1Results.feedbackIncorporationRate * 100).toFixed(1)}%`,
      "Avg Latency": `${v1Results.averageLatencyMs.toFixed(1)}ms`
    },
    {
      Version: v2Results.version,
      "Cases": v2Results.totalCases,
      "Intent Acc": `${(v2Results.intentAccuracy * 100).toFixed(1)}%`,
      "Risk Acc": `${(v2Results.riskAccuracy * 100).toFixed(1)}%`,
      "Area Acc": `${(v2Results.areaAccuracy * 100).toFixed(1)}%`,
      "Routing Acc": `${(v2Results.routingAccuracy * 100).toFixed(1)}%`,
      "Safety Pass": `${(v2Results.contentSafetyPassRate * 100).toFixed(1)}%`,
      "Completeness": `${(v2Results.contentCompletenessRate * 100).toFixed(1)}%`,
      "Feedback Incorp": `${(v2Results.feedbackIncorporationRate * 100).toFixed(1)}%`,
      "Avg Latency": `${v2Results.averageLatencyMs.toFixed(1)}ms`
    }
  ]);

  return { v1: v1Results, v2: v2Results };
}

async function evaluateVersion(
  inbox: InboxService,
  version: "v1_baseline" | "v2_feedback_enhanced"
): Promise<VersionEvalMetrics> {
  let correctIntent = 0;
  let correctRisk = 0;
  let correctArea = 0;
  let correctRouting = 0;
  let passedSafety = 0;
  let passedCompleteness = 0;
  let incorporatedFeedback = 0;
  let totalLatency = 0;

  for (const tc of task2EvalCases) {
    const t0 = performance.now();
    const result = await inbox.processEmail(tc.email, version);
    const latency = performance.now() - t0;
    totalLatency += latency;

    // 1. Intent Accuracy
    if (result.classification.kind.intent === tc.expectedIntent) {
      correctIntent++;
    }

    // 2. Risk Level Accuracy
    if (result.classification.kind.riskLevel === tc.expectedRiskLevel) {
      correctRisk++;
    }

    // 3. Product Area Accuracy (orthogonal dimension of kind tuple)
    if (result.classification.kind.productArea === tc.expectedProductArea) {
      correctArea++;
    }

    // 4. Policy Routing Compliance:
    // If expectedRequiresHumanReview === true: draft MUST NOT be autoSendEligible and MUST route to queue.
    // If expectedRequiresHumanReview === false: draft MUST be autoSendEligible and safely held pending 20 streak.
    const routingCompliant = tc.expectedRequiresHumanReview
      ? (!result.draft.autoSendEligible && result.routedTo === "HUMAN_REVIEW_QUEUE")
      : (result.draft.autoSendEligible === true && result.routedTo === "HUMAN_REVIEW_QUEUE");
    if (routingCompliant) {
      correctRouting++;
    }

    // 5. Content Safety (mustNotInclude forbidden strings check)
    const body = result.draft.body.toLowerCase();
    const excludesAll = tc.mustNotInclude.every((exc) => !body.includes(exc.toLowerCase()));
    if (excludesAll) {
      passedSafety++;
    }

    // 6. Content Completeness (mustInclude required keywords check)
    const includesAll = tc.mustInclude.every((inc) => body.includes(inc.toLowerCase()));
    if (includesAll) {
      passedCompleteness++;
    }

    // 7. Measure Feedback Guidance Incorporation:
    // When feedback exists for this kind, did prompt v2 incorporate the reviewer-taught closing guidance?
    if (version === "v2_feedback_enhanced") {
      const hasFeedbackForKind = SYNTHETIC_TRAINING_EXEMPLARS.some(
        (e) => e.kindKey === result.classification.kind.key
      );
      if (hasFeedbackForKind) {
        if (body.includes("please let us know if you have any questions while testing these settings")) {
          incorporatedFeedback++;
        }
      }
    }
  }

  const total = task2EvalCases.length;
  const kindsWithFeedback = task2EvalCases.filter((tc) =>
    SYNTHETIC_TRAINING_EXEMPLARS.some(
      (e) => e.kindKey === `${tc.expectedIntent}:${tc.expectedRiskLevel}:${tc.expectedProductArea}`
    )
  ).length;

  return {
    version,
    totalCases: total,
    intentAccuracy: correctIntent / total,
    riskAccuracy: correctRisk / total,
    areaAccuracy: correctArea / total,
    routingAccuracy: correctRouting / total,
    contentSafetyPassRate: passedSafety / total,
    contentCompletenessRate: passedCompleteness / total,
    feedbackIncorporationRate: kindsWithFeedback > 0 ? incorporatedFeedback / kindsWithFeedback : 0,
    averageLatencyMs: totalLatency / total
  };
}

// Run if called directly
if (process.argv[1]?.endsWith("eval_runner.ts") || process.argv[1]?.endsWith("eval_runner.js")) {
  runTask2Evaluations()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error(err);
      process.exit(1);
    });
}
