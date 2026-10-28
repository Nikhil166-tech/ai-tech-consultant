import { EmailClassifier } from "../src/classification/classifier.js";
import { task2EvalCases, Task2EvalCase } from "./task2_eval_suite.js";
import { Intent, RiskLevel, ProductArea } from "../src/types/index.js";

export interface Step4EvalMetrics {
  totalCases: number;
  intentAccuracy: number;
  riskAccuracy: number;
  parentLabelAccuracy: number;
  specificLabelAccuracy: number;
  parentConsistencyRate: number;
  unknownHandlingRate: number;
  unsafeDetectionRate: number;
  humanReviewRoutingRate: number;
  macroF1: number;
  averageLatencyMs: number;
  totalTokens: number;
  estimatedCostUsd: number;
  modelUsed: string;
  provider: string;
  liveStatus: "LIVE" | "MOCK" | "BLOCKED";
}

export async function runStep4ClassificationEvaluations(): Promise<Step4EvalMetrics> {
  console.log("================================================================================");
  console.log("      STEP 4 REPRODUCIBLE EVALUATION: 50-CASE AI CLASSIFICATION BENCHMARK       ");
  console.log("================================================================================");

  const classifier = new EmailClassifier();
  const cases = task2EvalCases;

  let correctIntent = 0;
  let correctRisk = 0;
  let correctParent = 0;
  let correctSpecific = 0;
  let consistentParentChild = 0;
  let correctUnknown = 0;
  let correctUnsafe = 0;
  let correctHumanReview = 0;
  let totalLatencyMs = 0;
  let totalTokens = 0;
  let totalCostUsd = 0;

  // Track per-intent true positives, false positives, false negatives for Macro F1
  const intentStats: Record<string, { tp: number; fp: number; fn: number }> = {};
  for (const intent of Object.values(Intent)) {
    intentStats[intent] = { tp: 0, fp: 0, fn: 0 };
  }

  const startTime = Date.now();
  let modelsObserved = new Set<string>();
  let providersObserved = new Set<string>();

  for (const c of cases) {
    const caseStart = Date.now();
    const res = await classifier.classifyAsync(c.email);
    const latency = Date.now() - caseStart;
    totalLatencyMs += latency;

    if (res.classificationModel) modelsObserved.add(res.classificationModel);
    if (res.classificationProvider) providersObserved.add(res.classificationProvider);

    // Intent accuracy
    const predictedIntent = res.kind.intent;
    if (predictedIntent === c.expectedIntent) {
      correctIntent++;
      intentStats[c.expectedIntent].tp++;
    } else {
      intentStats[c.expectedIntent].fn++;
      if (intentStats[predictedIntent]) intentStats[predictedIntent].fp++;
    }

    // Risk accuracy
    if (res.kind.riskLevel === c.expectedRiskLevel) {
      correctRisk++;
    }

    // Parent & Specific Label accuracy
    if (c.expectedParentSettingType && res.parentSettingType === c.expectedParentSettingType) {
      correctParent++;
    }
    if (c.expectedSpecificLabel && res.specificLabel === c.expectedSpecificLabel) {
      correctSpecific++;
    }

    // Parent consistency: does specific label belong to parentSettingType in taxonomy?
    const tax = classifier.getTaxonomy();
    const match = tax.find(
      (t) => t.parentSettingType === res.parentSettingType && t.specificLabel === res.specificLabel
    );
    if (match) {
      consistentParentChild++;
    }

    // Unknown handling (e.g. Kubernetes, Solana, Drones)
    if (["T2-EVAL-36", "T2-EVAL-37", "T2-EVAL-38"].includes(c.id)) {
      if (res.requiresHumanReview && res.uncertaintyIndicator) {
        correctUnknown++;
      }
    }

    // Unsafe / prompt injection detection
    if (c.expectedRiskLevel === RiskLevel.CRITICAL) {
      if (res.kind.riskLevel === RiskLevel.CRITICAL && res.requiresHumanReview) {
        correctUnsafe++;
      }
    }

    // Human review routing
    if (res.requiresHumanReview === c.expectedRequiresHumanReview) {
      correctHumanReview++;
    }
  }

  // Calculate Macro F1
  let f1Sum = 0;
  let validIntentsCount = 0;
  for (const stats of Object.values(intentStats)) {
    const precision = stats.tp + stats.fp > 0 ? stats.tp / (stats.tp + stats.fp) : 0;
    const recall = stats.tp + stats.fn > 0 ? stats.tp / (stats.tp + stats.fn) : 0;
    const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
    if (stats.tp + stats.fn > 0) {
      f1Sum += f1;
      validIntentsCount++;
    }
  }
  const macroF1 = validIntentsCount > 0 ? f1Sum / validIntentsCount : 0;

  // Determine live status
  const hasLiveApiKey = Boolean(process.env.GEMINI_API_KEY || process.env.ANTHROPIC_API_KEY);
  const liveStatus: "LIVE" | "MOCK" | "BLOCKED" = hasLiveApiKey ? "LIVE" : "BLOCKED";

  const metrics: Step4EvalMetrics = {
    totalCases: cases.length,
    intentAccuracy: Math.round((correctIntent / cases.length) * 1000) / 10,
    riskAccuracy: Math.round((correctRisk / cases.length) * 1000) / 10,
    parentLabelAccuracy: Math.round((correctParent / cases.filter(c => c.expectedParentSettingType).length) * 1000) / 10,
    specificLabelAccuracy: Math.round((correctSpecific / cases.filter(c => c.expectedSpecificLabel).length) * 1000) / 10,
    parentConsistencyRate: Math.round((consistentParentChild / cases.length) * 1000) / 10,
    unknownHandlingRate: Math.round((correctUnknown / 3) * 1000) / 10,
    unsafeDetectionRate: Math.round((correctUnsafe / cases.filter(c => c.expectedRiskLevel === RiskLevel.CRITICAL).length) * 1000) / 10,
    humanReviewRoutingRate: Math.round((correctHumanReview / cases.length) * 1000) / 10,
    macroF1: Math.round(macroF1 * 1000) / 1000,
    averageLatencyMs: Math.round(totalLatencyMs / cases.length),
    totalTokens,
    estimatedCostUsd: Math.round(totalCostUsd * 1000) / 1000,
    modelUsed: Array.from(modelsObserved).join(", ") || "deterministic_keyword_fallback",
    provider: Array.from(providersObserved).join(", ") || "deterministic",
    liveStatus
  };

  console.log(`- Total Cases Evaluated: ${metrics.totalCases}`);
  console.log(`- Intent Accuracy: ${metrics.intentAccuracy}%`);
  console.log(`- Risk Tier Accuracy: ${metrics.riskAccuracy}%`);
  console.log(`- Parent Consistency Rate: ${metrics.parentConsistencyRate}%`);
  console.log(`- Unknown Topic Handling Rate: ${metrics.unknownHandlingRate}%`);
  console.log(`- Unsafe / Prompt Injection Detection: ${metrics.unsafeDetectionRate}%`);
  console.log(`- Human Review Routing Rate: ${metrics.humanReviewRoutingRate}%`);
  console.log(`- Macro F1 Score: ${metrics.macroF1}`);
  console.log(`- Average Latency: ${metrics.averageLatencyMs}ms`);
  console.log(`- Execution Mode: ${metrics.liveStatus} (Models: ${metrics.modelUsed})`);
  console.log("================================================================================\n");

  return metrics;
}

if (process.argv[1]?.includes("step4_eval_runner")) {
  runStep4ClassificationEvaluations()
    .then(() => process.exit(0))
    .catch((err) => {
      console.error("Evaluation execution failed:", err);
      process.exit(1);
    });
}
