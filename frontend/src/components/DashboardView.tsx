import React from "react";
import {
  BookOpen,
  Globe,
  Inbox,
  AlertOctagon,
  Flame,
  CheckCircle2,
  ArrowRight,
  Sparkles,
  ShieldCheck,
  TrendingUp,
  ExternalLink
} from "lucide-react";
import { ViewType } from "./Sidebar";
import { SitemapItem } from "../types";

interface DashboardViewProps {
  articlesCount: number;
  sitemapsCount: number;
  quarantinedCount: number;
  interactionsCount: number;
  pendingReviewCount: number;
  labelStates: any[];
  sitemaps?: SitemapItem[];
  onNavigate: (view: ViewType) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  articlesCount,
  sitemapsCount,
  quarantinedCount,
  interactionsCount,
  pendingReviewCount,
  labelStates,
  sitemaps = [],
  onNavigate
}) => {
  const qualifiedLabels = labelStates.filter((l) => l.autonomyEnabled && l.unchangedStreak >= l.requiredThreshold);

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8">
      {/* Hero Welcome */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-xl relative overflow-hidden">
        <div className="space-y-2 max-w-2xl">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-sky-500/10 border border-sky-500/30 text-sky-400 text-xs font-semibold">
            <Sparkles className="w-3.5 h-3.5" />
            <span>AI Tech Consultant Enterprise Brain v2.2</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-100">
            Autonomous Technical Support & Knowledge Intelligence
          </h1>
          <p className="text-xs text-slate-400 leading-relaxed">
            Local zero-data-loss crawler, hybrid semantic RAG engine, Gmail-style inbox automation, and independent per-label HITL guardrails.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <button
            onClick={() => onNavigate("chat")}
            className="px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/20 transition flex items-center justify-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            <span>Ask Doubt</span>
          </button>
          <button
            onClick={() => onNavigate("reviews")}
            className="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-semibold transition flex items-center justify-center gap-2"
          >
            <span>Review Queue</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <button
          onClick={() => onNavigate("knowledge")}
          className="text-left bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-5 space-y-2 transition shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase">Active Knowledge</span>
            <BookOpen className="w-4 h-4 text-sky-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100">{articlesCount}</div>
          <span className="text-[11px] text-slate-500 block">Indexed & searchable articles</span>
        </button>

        <button
          onClick={() => onNavigate("sitemaps")}
          className="text-left bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-5 space-y-2 transition shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase">Monitored Sitemaps</span>
            <Globe className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100">{sitemapsCount}</div>
          <span className="text-[11px] text-slate-500 block">Multi-URL discovery trees</span>
        </button>

        <button
          onClick={() => onNavigate("inbox")}
          className="text-left bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-5 space-y-2 transition shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase">Processed Emails</span>
            <Inbox className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100">{interactionsCount}</div>
          <span className="text-[11px] text-emerald-400/80 block">
            {pendingReviewCount} awaiting human review
          </span>
        </button>

        <button
          onClick={() => onNavigate("quarantine")}
          className="text-left bg-slate-900 border border-slate-800 hover:border-slate-700 rounded-xl p-5 space-y-2 transition shadow-sm"
        >
          <div className="flex items-center justify-between text-slate-400">
            <span className="text-xs font-semibold uppercase">Quarantined URLs</span>
            <AlertOctagon className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-slate-100">{quarantinedCount}</div>
          <span className="text-[11px] text-amber-400/80 block">Isolated (zero data loss)</span>
        </button>
      </div>

      {/* Monitored Knowledge Sitemaps on Dashboard */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Globe className="w-4 h-4 text-sky-400" />
              <span>Monitored Knowledge Sources ({sitemaps.length})</span>
            </h2>
            <p className="text-[11px] text-slate-400">
              Active crawling roots and documentation sources feeding the Knowledge Brain.
            </p>
          </div>
          <button
            onClick={() => onNavigate("sitemaps")}
            className="text-xs text-sky-400 hover:text-sky-300 font-medium flex items-center gap-1"
          >
            <span>Manage All Sitemaps</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {sitemaps.length === 0 ? (
          <div className="p-6 text-center text-slate-500 text-xs">
            No sitemaps registered yet. Click "Manage All Sitemaps" to add and index a documentation URL.
          </div>
        ) : (
          <div className="space-y-3">
            {sitemaps.map((sm) => {
              const url = sm.url || sm.root_url || "";
              const isIndexing = (sm.status || "").toLowerCase() === "indexing" || sm.current_run_status === "running";
              return (
                <div
                  key={sm.id}
                  className="p-4 bg-slate-950 border border-slate-800 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-bold text-sky-400 hover:text-sky-300 hover:underline font-mono truncate max-w-md flex items-center gap-1"
                      >
                        <span>{sm.name || url}</span>
                        <ExternalLink className="w-3 h-3 text-slate-400 shrink-0" />
                      </a>
                      <span
                        className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase flex items-center gap-1 ${isIndexing
                            ? "bg-amber-950 text-amber-300 border border-amber-800 animate-pulse"
                            : (sm.status || "").toLowerCase() === "active" || (sm.status || "").toLowerCase() === "confirmed"
                              ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                              : "bg-sky-950 text-sky-300 border border-sky-800"
                          }`}
                      >
                        {isIndexing && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />}
                        {isIndexing ? `Indexing (${sm.progress_percent || 0}%)` : (sm.status || "Registered")}
                      </span>
                    </div>

                    <div className="text-[11px] text-slate-400 flex items-center gap-3">
                      <span>Total URLs: <strong className="text-slate-200">{sm.total_urls_count || "Pending"}</strong></span>
                      <span>•</span>
                      <span>Frequency: <strong className="text-slate-200">{sm.refresh_interval || "daily"}</strong></span>
                      {sm.last_validated_at && (
                        <>
                          <span>•</span>
                          <span>Last Sync: {new Date(sm.last_validated_at).toLocaleDateString()}</span>
                        </>
                      )}
                    </div>

                    {isIndexing && (
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden mt-2">
                        <div
                          className="bg-sky-500 h-1.5 rounded-full transition-all duration-500"
                          style={{ width: `${Math.max(5, sm.progress_percent || 0)}%` }}
                        />
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => onNavigate("sitemaps")}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold border border-slate-700 transition"
                    >
                      View Details
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Autonomy Readiness Section */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Flame className="w-4 h-4 text-amber-400" />
              <span>Independent Autonomy Status</span>
            </h2>
            <p className="text-[11px] text-slate-400">
              Labels qualify for autonomous sending once they achieve X consecutive unchanged approvals.
            </p>
          </div>
          <button
            onClick={() => onNavigate("analytics")}
            className="text-xs text-sky-400 hover:text-sky-300 font-medium flex items-center gap-1"
          >
            <span>View All Streaks</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-400 text-xs font-semibold">Active Autonomous Labels</span>
            <div className="text-xl font-bold text-emerald-400">{qualifiedLabels.length} qualifying</div>
            <span className="text-[10px] text-slate-500">Safe low-risk autonomous delivery</span>
          </div>

          <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-400 text-xs font-semibold">Pending Approval Streaks</span>
            <div className="text-xl font-bold text-sky-400">{labelStates.length - qualifiedLabels.length} in progress</div>
            <span className="text-[10px] text-slate-500">Streaks building toward threshold X</span>
          </div>

          <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
            <span className="text-slate-400 text-xs font-semibold">Human Review Required</span>
            <div className="text-xl font-bold text-amber-400">{pendingReviewCount} items</div>
            <span className="text-[10px] text-slate-500">Awaiting specialist approval</span>
          </div>
        </div>
      </div>
    </div>
  );
};
