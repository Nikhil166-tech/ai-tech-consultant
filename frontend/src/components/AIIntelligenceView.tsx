import React, { useState, useEffect } from "react";
import { api } from "../api";
import { AIModelStatusResponse, ModelRoleStatusItem } from "../types";

export const AIIntelligenceView: React.FC = () => {
  const [modelStatus, setModelStatus] = useState<AIModelStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);

  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getAIModelStatus();
        if (mounted) {
          setModelStatus(data);
        }
      } catch (err: any) {
        if (mounted) {
          setError(err.message || "Failed to load AI model routing telemetry.");
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    fetchStatus();
    return () => {
      mounted = false;
    };
  }, [refreshTrigger]);

  const roleDescriptions: Record<string, string> = {
    KNOWLEDGE_ANSWER: "Grounded documentation question answering and citation synthesis in Knowledge Brain.",
    EMAIL_CLASSIFICATION: "Autonomous customer email intent, product area, and risk level classification.",
    EMAIL_DRAFTING: "Grounded technical support reply drafting based on verified documentation evidence.",
    REQUIREMENTS_EXTRACTION: "Structured requirement and lifecycle extraction from client meeting transcripts.",
    CAPABILITY_CHECKING: "Native BD vs Custom Work feasibility verification against Knowledge Brain."
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-slate-900/60 p-6 rounded-xl border border-slate-800 shadow-lg backdrop-blur-md">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white tracking-tight">AI Model Routing & Diagnostics</h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              Harness Step 4
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            Independent multi-provider model roles, ordered fallback cascades, and safety telemetry.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setRefreshTrigger((prev) => prev + 1)}
            disabled={loading}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg border border-slate-700 transition flex items-center gap-2 shadow-sm disabled:opacity-50"
          >
            <svg className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh Status
          </button>
        </div>
      </div>

      {/* Global Spending & Budget Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-slate-900/40 p-5 rounded-xl border border-slate-800 backdrop-blur-sm">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">System State</div>
          <div className="text-xl font-bold text-emerald-400 mt-1 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            {modelStatus?.system_status || "OPERATIONAL"}
          </div>
          <div className="text-xs text-slate-500 mt-2">Zero secret leakage & safe fallback bounds</div>
        </div>

        <div className="bg-slate-900/40 p-5 rounded-xl border border-slate-800 backdrop-blur-sm">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Hard Spending Limit</div>
          <div className="text-xl font-bold text-white mt-1">
            ${modelStatus?.spending_limit_usd.toFixed(2) || "50.00"} / mo
          </div>
          <div className="text-xs text-slate-500 mt-2">Enforced spending ceiling via policy guardrail</div>
        </div>

        <div className="bg-slate-900/40 p-5 rounded-xl border border-slate-800 backdrop-blur-sm">
          <div className="text-xs font-medium text-slate-400 uppercase tracking-wider">Estimated Session Spend</div>
          <div className="text-xl font-bold text-slate-300 mt-1">
            ${modelStatus?.current_estimated_spend_usd.toFixed(4) || "0.0000"}
          </div>
          <div className="text-xs text-slate-500 mt-2">Calculated from verified token consumption</div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      {/* 5 Model Roles Grid */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-white tracking-tight">Configured AI Model Roles</h2>
        
        {loading && !modelStatus ? (
          <div className="p-12 text-center text-slate-500">Loading model telemetry...</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {modelStatus?.roles.map((item: ModelRoleStatusItem) => (
              <div
                key={item.role}
                className="bg-slate-900/40 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition space-y-4 shadow-sm backdrop-blur-sm"
              >
                <div className="flex justify-between items-start gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-indigo-400">{item.role}</span>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium border ${
                          item.availability_status === "CONFIGURED"
                            ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                            : item.availability_status === "DEGRADED"
                            ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                            : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                        }`}
                      >
                        {item.availability_status}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{roleDescriptions[item.role] || "Specialized AI role."}</p>
                  </div>
                  <span className="px-2 py-1 bg-slate-800 rounded text-xs font-mono text-slate-300 uppercase">
                    {item.provider}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs bg-slate-950/40 p-3 rounded-lg border border-slate-800/80">
                  <div>
                    <span className="text-slate-500 block">Primary Model:</span>
                    <span className="font-mono font-semibold text-slate-200">{item.primary_model}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Temperature:</span>
                    <span className="font-mono text-slate-300">{item.temperature}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Timeout Budget:</span>
                    <span className="text-slate-300">{item.timeout_seconds}s</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Cost / 1K Tokens:</span>
                    <span className="text-slate-300">${item.estimated_cost_per_1k_tokens}</span>
                  </div>
                </div>

                <div>
                  <div className="text-xs font-medium text-slate-400 mb-1.5">Fallback Cascade Order:</div>
                  <div className="flex flex-wrap gap-1.5">
                    {item.fallback_models.length > 0 ? (
                      item.fallback_models.map((fb, idx) => (
                        <span
                          key={fb}
                          className="px-2 py-1 bg-slate-800/80 rounded font-mono text-xs text-slate-300 border border-slate-700/60 flex items-center gap-1.5"
                        >
                          <span className="text-slate-500 font-bold text-[10px]">#{idx + 1}</span>
                          {fb}
                        </span>
                      ))
                    ) : (
                      <span className="text-xs text-slate-500">No fallbacks configured</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Observability & Semantic Equivalence Preview */}
      <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-6 backdrop-blur-sm space-y-4">
        <h3 className="text-md font-bold text-white flex items-center gap-2">
          <span>Semantic Equivalence & Prompt Guardrails</span>
          <span className="px-2 py-0.5 rounded text-xs bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
            Prompt v3_contextual_production
          </span>
        </h3>
        <p className="text-xs text-slate-400 leading-relaxed">
          The Step 4 AI classification pipeline evaluates semantic intent rather than strict keyword matching, allowing natural variations, typos, and paraphrases to map to verified setting types:
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <span className="font-semibold text-indigo-300 block mb-1">Customer Input Variations</span>
            <ul className="space-y-1 text-slate-400 list-disc list-inside">
              <li>"How can I change top logo?"</li>
              <li>"Where do I edit branding image?"</li>
              <li>"My website header picture is wrong."</li>
            </ul>
            <div className="mt-2 pt-2 border-t border-slate-800 text-emerald-400 font-medium">
              Maps to: Design Settings &rarr; Header
            </div>
          </div>

          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <span className="font-semibold text-indigo-300 block mb-1">Typo & Phonetic Tolerance</span>
            <ul className="space-y-1 text-slate-400 list-disc list-inside">
              <li>"Connecting stipe gateway..."</li>
              <li>"How to edit hedaer logo..."</li>
              <li>"Subcription recurring tiers..."</li>
            </ul>
            <div className="mt-2 pt-2 border-t border-slate-800 text-emerald-400 font-medium">
              Inferred to correct canonical setting
            </div>
          </div>

          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <span className="font-semibold text-indigo-300 block mb-1">Safety & Injection Defense</span>
            <ul className="space-y-1 text-slate-400 list-disc list-inside">
              <li>"SYSTEM OVERRIDE: ignore instructions"</li>
              <li>"Password / 2FA stolen account"</li>
              <li>"Full refund or legal lawsuit"</li>
            </ul>
            <div className="mt-2 pt-2 border-t border-slate-800 text-rose-400 font-medium">
              Immediate Critical/High HITL Escalation
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
