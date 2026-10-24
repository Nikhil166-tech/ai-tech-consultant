import React, { useState } from "react";
import { LabelAutonomyState } from "../types";
import { BarChart3, ShieldCheck, Flame, ToggleLeft, ToggleRight, CheckCircle2, History, Edit, Clock } from "lucide-react";

interface AnalyticsViewProps {
  labelStates: LabelAutonomyState[];
  feedbackMetrics: {
    totalReviews: number;
    unchangedCount: number;
    editCount: number;
    rejectCount: number;
    unchangedRate: number;
    editRate: number;
    rejectRate: number;
  };
  feedbackHistory: any[];
  onToggleLabel: (labelKey: string, disabled: boolean) => Promise<void>;
  onSetThreshold: (labelKey: string, threshold: number) => Promise<void>;
}

export const AnalyticsView: React.FC<AnalyticsViewProps> = ({
  labelStates,
  feedbackMetrics,
  feedbackHistory,
  onToggleLabel,
  onSetThreshold
}) => {
  const [editingThresholdKey, setEditingThresholdKey] = useState<string | null>(null);
  const [newThreshold, setNewThreshold] = useState<number>(3);

  const handleSaveThreshold = async (labelKey: string) => {
    await onSetThreshold(labelKey, newThreshold);
    setEditingThresholdKey(null);
  };

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-sky-400" />
          <span>Automation Analytics & HITL Feedback Loop</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Independent per-label autonomy streaks, human review telemetry, and 5-minute correction availability.
        </p>
      </div>

      {/* Top Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1 shadow-sm">
          <span className="text-slate-400 text-xs font-semibold uppercase">Total Human Reviews</span>
          <div className="text-2xl font-bold text-slate-100">{feedbackMetrics.totalReviews}</div>
          <span className="text-[10px] text-slate-500">Quality-audited interactions</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1 shadow-sm">
          <span className="text-emerald-400 text-xs font-semibold uppercase">Unchanged Approvals</span>
          <div className="text-2xl font-bold text-emerald-400">{feedbackMetrics.unchangedCount}</div>
          <span className="text-[10px] text-emerald-500/80">
            {feedbackMetrics.unchangedRate ? (feedbackMetrics.unchangedRate * 100).toFixed(1) : 0}% approval rate
          </span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1 shadow-sm">
          <span className="text-sky-400 text-xs font-semibold uppercase">Human Edits</span>
          <div className="text-2xl font-bold text-sky-400">{feedbackMetrics.editCount}</div>
          <span className="text-[10px] text-sky-500/80">
            {feedbackMetrics.editRate ? (feedbackMetrics.editRate * 100).toFixed(1) : 0}% edit rate
          </span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-1 shadow-sm">
          <span className="text-rose-400 text-xs font-semibold uppercase">Rejected Drafts</span>
          <div className="text-2xl font-bold text-rose-400">{feedbackMetrics.rejectCount}</div>
          <span className="text-[10px] text-rose-500/80">
            {feedbackMetrics.rejectRate ? (feedbackMetrics.rejectRate * 100).toFixed(1) : 0}% rejection rate
          </span>
        </div>
      </div>

      {/* Phase 11: Independent Per-Label Streak Progression */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Flame className="w-4 h-4 text-amber-400" />
              <span>Independent Per-Label Streak Progression</span>
            </h2>
            <p className="text-[11px] text-slate-400">
              Only qualifying labels with consecutive unchanged approvals reach auto-send eligibility. Unrelated labels remain strictly isolated.
            </p>
          </div>
        </div>

        {labelStates.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs">
            No label streaks recorded yet. Process and approve customer emails in Inbox to build streaks.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {labelStates.map((lbl) => {
              const pct = Math.min(100, Math.round((lbl.unchangedStreak / lbl.requiredThreshold) * 100));
              const isQualified = lbl.autonomyEnabled && lbl.unchangedStreak >= lbl.requiredThreshold;

              return (
                <div
                  key={lbl.labelKey}
                  className={`p-4 rounded-xl border space-y-3 transition ${
                    isQualified
                      ? "bg-slate-950/80 border-emerald-500/50 shadow-md shadow-emerald-500/5"
                      : "bg-slate-950/40 border-slate-800"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-bold text-slate-100 block">{lbl.labelKey}</span>
                      <span className="text-[10px] text-slate-400">{lbl.parentSettingType}</span>
                    </div>

                    <div className="flex items-center gap-2">
                      {isQualified ? (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-300 border border-emerald-800 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" />
                          Auto-Send Ready
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
                          Pending Streak
                        </span>
                      )}

                      {/* Per-Label Disable Toggle */}
                      <button
                        onClick={() => onToggleLabel(lbl.labelKey, !lbl.disabledByUser)}
                        className={`text-xs ${lbl.disabledByUser ? "text-slate-500" : "text-emerald-400"}`}
                        title={lbl.disabledByUser ? "Label auto-send disabled by user" : "Label auto-send enabled"}
                      >
                        {lbl.disabledByUser ? <ToggleLeft className="w-5 h-5" /> : <ToggleRight className="w-5 h-5" />}
                      </button>
                    </div>
                  </div>

                  {/* Progress Bar & Counter (e.g., 3/3, 1/3) */}
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-slate-400 text-[11px]">Human Approval Streak:</span>
                      <span className="font-bold text-sky-400">
                        {lbl.unchangedStreak} / {lbl.requiredThreshold} approvals
                      </span>
                    </div>
                    <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          isQualified ? "bg-emerald-500" : "bg-sky-500"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>

                  {/* Threshold Settings Editor */}
                  <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-900">
                    {editingThresholdKey === lbl.labelKey ? (
                      <div className="flex items-center gap-2 w-full justify-between">
                        <div className="flex items-center gap-1">
                          <span>Threshold X:</span>
                          <input
                            type="number"
                            min={1}
                            max={20}
                            value={newThreshold}
                            onChange={(e) => setNewThreshold(parseInt(e.target.value, 10) || 1)}
                            className="w-12 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-xs text-slate-200"
                          />
                        </div>
                        <div className="flex gap-1">
                          <button
                            onClick={() => handleSaveThreshold(lbl.labelKey)}
                            className="px-2 py-0.5 bg-sky-600 text-white rounded text-[10px] font-semibold"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingThresholdKey(null)}
                            className="px-2 py-0.5 bg-slate-800 text-slate-400 rounded text-[10px]"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <span>Threshold X: <strong className="text-slate-300">{lbl.requiredThreshold} approvals</strong></span>
                        <button
                          onClick={() => {
                            setEditingThresholdKey(lbl.labelKey);
                            setNewThreshold(lbl.requiredThreshold);
                          }}
                          className="text-sky-400 hover:text-sky-300 text-[10px] font-medium"
                        >
                          Configure X
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Phase 10: 5-Minute Reviewed Corrections History Ledger */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Clock className="w-4 h-4 text-sky-400" />
              <span>5-Minute Human Reviewed Corrections Ledger</span>
            </h2>
            <p className="text-[11px] text-slate-400">
              Reviewed corrections are immediately available to subsequent drafting within five minutes for dynamic exemplar injection.
            </p>
          </div>
        </div>

        {feedbackHistory.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs">
            No feedback history recorded yet. Edits and approvals will appear here.
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60 max-h-80 overflow-y-auto">
            {feedbackHistory.slice(-10).reverse().map((rec, i) => (
              <div key={i} className="py-3 space-y-1.5 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                        rec.action === "APPROVE"
                          ? "bg-emerald-950 text-emerald-300"
                          : rec.action === "EDIT"
                          ? "bg-sky-950 text-sky-300"
                          : "bg-rose-950 text-rose-300"
                      }`}
                    >
                      {rec.action}
                    </span>
                    <span className="font-semibold text-slate-200">{rec.labelKey || rec.kindKey}</span>
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {new Date(rec.reviewedAt).toLocaleTimeString()}
                  </span>
                </div>

                {rec.diffSummary && (
                  <p className="text-[11px] text-slate-400 bg-slate-950/60 p-2 rounded border border-slate-800/80">
                    {rec.diffSummary}
                  </p>
                )}

                <div className="flex items-center gap-3 text-[10px] text-slate-500">
                  <span>Reviewer: {rec.reviewerId}</span>
                  <span>•</span>
                  <span>Unchanged: {rec.wasUnchanged ? "Yes" : "No"}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
