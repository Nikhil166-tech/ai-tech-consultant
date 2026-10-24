import React, { useState } from "react";
import { QuarantineRecord } from "../types";
import { AlertOctagon, RotateCcw, ShieldCheck, Search, Clock, ExternalLink, AlertTriangle } from "lucide-react";

interface QuarantineViewProps {
  quarantinedRecords: QuarantineRecord[];
  onRestore: (articleId: string) => Promise<void>;
  onRefreshData: () => void;
}

export const QuarantineView: React.FC<QuarantineViewProps> = ({
  quarantinedRecords,
  onRestore,
  onRefreshData
}) => {
  const [search, setSearch] = useState("");
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const filtered = quarantinedRecords.filter((rec) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return rec.url.toLowerCase().includes(q) || rec.title.toLowerCase().includes(q);
  });

  const handleRestore = async (articleId: string) => {
    setRestoringId(articleId);
    try {
      await onRestore(articleId);
      onRefreshData();
    } finally {
      setRestoringId(null);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <AlertOctagon className="w-5 h-5 text-amber-400" />
            <span>Quarantine Management</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Zero-loss isolation: Quarantined records are excluded from active RAG retrieval while keeping chunks and historical embeddings preserved intact.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg text-slate-300">
            Total Quarantined: <strong className="text-amber-400">{quarantinedRecords.length}</strong>
          </span>
        </div>
      </div>

      {/* Policy Notice */}
      <div className="p-4 bg-amber-950/20 border border-amber-800/40 rounded-xl text-xs text-amber-200/90 flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-amber-300 block">Strict Zero Data Loss Invariant</span>
          Indexed knowledge is never permanently destroyed on 404 or redirect. Content, embeddings, and headings remain preserved on disk and can be restored immediately with one click.
        </div>
      </div>

      {/* Filter / Search */}
      <div className="relative max-w-sm">
        <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
        <input
          type="text"
          placeholder="Search quarantined URL or title..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-slate-950 border border-slate-800 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-200 focus:outline-none focus:border-amber-500/60"
        />
      </div>

      {/* Quarantine Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs space-y-1">
            <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
            <p className="font-semibold text-slate-300">No quarantined records.</p>
            <p>All monitored URLs are active and healthy in the Knowledge Brain.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3.5">Title & URL</th>
                  <th className="p-3.5">Quarantine Reason</th>
                  <th className="p-3.5">HTTP Status</th>
                  <th className="p-3.5">Failures Count</th>
                  <th className="p-3.5">Quarantined At</th>
                  <th className="p-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {filtered.map((rec) => (
                  <tr key={rec.id} className="hover:bg-slate-800/30 transition">
                    <td className="p-3.5 max-w-xs">
                      <strong className="text-slate-100 block truncate">{rec.title}</strong>
                      <span className="text-[11px] text-slate-400 font-mono truncate block" title={rec.url}>
                        {rec.url}
                      </span>
                    </td>
                    <td className="p-3.5">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/60 text-amber-300">
                        {rec.quarantine_reason}
                      </span>
                    </td>
                    <td className="p-3.5 font-mono">
                      <span className="text-rose-400 font-bold">{rec.last_http_status || "404"}</span>
                    </td>
                    <td className="p-3.5 font-mono text-slate-300">
                      {rec.consecutive_failures} failures
                    </td>
                    <td className="p-3.5 text-slate-400 text-[11px]">
                      {new Date(rec.quarantined_at).toLocaleString()}
                    </td>
                    <td className="p-3.5 text-right">
                      <button
                        onClick={() => handleRestore(rec.article_id)}
                        disabled={restoringId === rec.article_id}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition disabled:opacity-50 ml-auto"
                        title="Restore this article back to active knowledge brain"
                      >
                        <RotateCcw className={`w-3.5 h-3.5 ${restoringId === rec.article_id ? "animate-spin" : ""}`} />
                        <span>{restoringId === rec.article_id ? "Restoring..." : "Restore to Active"}</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
