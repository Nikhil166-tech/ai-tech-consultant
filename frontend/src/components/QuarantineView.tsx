import React, { useState, useEffect } from "react";
import {
  QuarantineRecord,
  URLHealthStatus,
  ArchivedArticleItem,
  ArchivedArticleDetail,
  ArticleRedirectItem,
  ArticleHistoryItem
} from "../types";
import { api } from "../api";
import {
  AlertOctagon,
  RotateCcw,
  ShieldCheck,
  Search,
  Clock,
  ExternalLink,
  AlertTriangle,
  Activity,
  Archive,
  ArrowRight,
  History,
  CheckCircle2,
  XCircle,
  FileText,
  Filter,
  RefreshCw,
  X
} from "lucide-react";

interface QuarantineViewProps {
  quarantinedRecords: QuarantineRecord[];
  onRestore: (articleId: string) => Promise<void>;
  onRefreshData: () => void;
}

type TabType = "health" | "archive" | "quarantine" | "redirects";

export const QuarantineView: React.FC<QuarantineViewProps> = ({
  quarantinedRecords,
  onRestore,
  onRefreshData
}) => {
  const [activeTab, setActiveTab] = useState<TabType>("health");

  // Health state
  const [healthItems, setHealthItems] = useState<URLHealthStatus[]>([]);
  const [healthSearch, setHealthSearch] = useState("");
  const [healthStatusFilter, setHealthStatusFilter] = useState("ALL");
  const [loadingHealth, setLoadingHealth] = useState(false);

  // Archive state
  const [archiveItems, setArchiveItems] = useState<ArchivedArticleItem[]>([]);
  const [archiveSearch, setArchiveSearch] = useState("");
  const [archiveReasonFilter, setArchiveReasonFilter] = useState("ALL");
  const [loadingArchive, setLoadingArchive] = useState(false);
  const [selectedArchiveDetail, setSelectedArchiveDetail] = useState<ArchivedArticleDetail | null>(null);
  const [loadingArchiveDetail, setLoadingArchiveDetail] = useState(false);

  // Redirects state
  const [redirects, setRedirects] = useState<ArticleRedirectItem[]>([]);
  const [loadingRedirects, setLoadingRedirects] = useState(false);

  // Version History state
  const [historyUrl, setHistoryUrl] = useState<string | null>(null);
  const [versionItems, setVersionItems] = useState<ArticleHistoryItem[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [selectedDiff, setSelectedDiff] = useState<string | null>(null);

  // Quarantine Search
  const [quarantineSearch, setQuarantineSearch] = useState("");
  const [restoringId, setRestoringId] = useState<string | null>(null);

  // Load URL health
  const loadHealthData = async () => {
    setLoadingHealth(true);
    try {
      const data = await api.listHealthObservations({
        search: healthSearch || undefined,
        status: healthStatusFilter !== "ALL" ? healthStatusFilter : undefined,
        limit: 100
      });
      setHealthItems(data);
    } catch (err) {
      console.warn("Failed to load health items:", err);
    } finally {
      setLoadingHealth(false);
    }
  };

  // Load Archive data
  const loadArchiveData = async () => {
    setLoadingArchive(true);
    try {
      const data = await api.listArchivedArticles({
        search: archiveSearch || undefined,
        reason: archiveReasonFilter !== "ALL" ? archiveReasonFilter : undefined,
        limit: 100
      });
      setArchiveItems(data);
    } catch (err) {
      console.warn("Failed to load archive items:", err);
    } finally {
      setLoadingArchive(false);
    }
  };

  // Load Redirects data
  const loadRedirectsData = async () => {
    setLoadingRedirects(true);
    try {
      const data = await api.listRedirects(100, 0);
      setRedirects(data);
    } catch (err) {
      console.warn("Failed to load redirects:", err);
    } finally {
      setLoadingRedirects(false);
    }
  };

  useEffect(() => {
    if (activeTab === "health") loadHealthData();
    if (activeTab === "archive") loadArchiveData();
    if (activeTab === "redirects") loadRedirectsData();
  }, [activeTab]);

  const handleCancelPending = async (url: string) => {
    try {
      await api.cancelPendingHealthAction(url);
      loadHealthData();
    } catch (err: any) {
      alert(`Cancel pending action failed: ${err.message}`);
    }
  };

  const handleReverifyUrl = async (url: string) => {
    try {
      const res = await api.reverifyUrl(url);
      alert(`Re-verification complete: HTTP ${res.http_status} (${res.is_healthy ? "Healthy" : "Unhealthy"})`);
      loadHealthData();
    } catch (err: any) {
      alert(`Re-verify failed: ${err.message}`);
    }
  };

  const handleViewArchiveDetail = async (itemId: string) => {
    setLoadingArchiveDetail(true);
    try {
      const detail = await api.getArchivedArticleDetail(itemId);
      setSelectedArchiveDetail(detail);
    } catch (err: any) {
      alert(`Failed to load archive detail: ${err.message}`);
    } finally {
      setLoadingArchiveDetail(false);
    }
  };

  const handleRestoreArchive = async (itemId: string) => {
    try {
      await api.restoreArchivedArticle(itemId);
      alert("Article successfully restored to active knowledge brain!");
      setSelectedArchiveDetail(null);
      loadArchiveData();
      onRefreshData();
    } catch (err: any) {
      alert(`Restore failed: ${err.message}`);
    }
  };

  const handleUpdateRetention = async (itemId: string, preset: string, customDays?: number) => {
    try {
      await api.updateArchiveRetention(itemId, preset, customDays);
      loadArchiveData();
      if (selectedArchiveDetail && selectedArchiveDetail.id === itemId) {
        setSelectedArchiveDetail({
          ...selectedArchiveDetail,
          retention_preset: preset,
          retention_days: customDays || (preset === "2_days" ? 2 : preset === "15_days" ? 15 : 30)
        });
      }
    } catch (err: any) {
      alert(`Update retention failed: ${err.message}`);
    }
  };

  const handleViewHistory = async (url: string) => {
    setHistoryUrl(url);
    setLoadingVersions(true);
    try {
      const data = await api.getArticleHistory(url);
      setVersionItems(data);
    } catch (err: any) {
      alert(`Failed to fetch history: ${err.message}`);
    } finally {
      setLoadingVersions(false);
    }
  };

  const handleViewDiff = async (v1Id: string, v2Id: string) => {
    try {
      const diffData = await api.getArticleHistoryDiff(v1Id, v2Id);
      setSelectedDiff(diffData.diff_text || "No differences detected.");
    } catch (err: any) {
      alert(`Failed to compute diff: ${err.message}`);
    }
  };

  const handleRestoreQuarantine = async (articleId: string) => {
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
      {/* Top Banner */}
      <div className="border-b border-slate-800 pb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Activity className="w-5 h-5 text-sky-400" />
            <span>URL Health, Lifecycle & Archived Knowledge</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Zero-loss lifecycle management: scheduled health verification, automatic 404 quarantine thresholds, 301 safe re-indexing, and recoverable archive storage.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg text-slate-300">
            Quarantined: <strong className="text-amber-400">{quarantinedRecords.length}</strong>
          </span>
          <span className="text-xs bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-lg text-slate-300">
            Archived: <strong className="text-sky-400">{archiveItems.length}</strong>
          </span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 space-x-1">
        <button
          onClick={() => setActiveTab("health")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition ${
            activeTab === "health"
              ? "border-sky-500 text-sky-400 bg-slate-800/40"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>URL Health Dashboard</span>
        </button>

        <button
          onClick={() => setActiveTab("archive")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition ${
            activeTab === "archive"
              ? "border-sky-500 text-sky-400 bg-slate-800/40"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <Archive className="w-4 h-4" />
          <span>Archived Knowledge Base</span>
        </button>

        <button
          onClick={() => setActiveTab("quarantine")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition ${
            activeTab === "quarantine"
              ? "border-sky-500 text-sky-400 bg-slate-800/40"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <AlertOctagon className="w-4 h-4" />
          <span>Quarantine & 404s</span>
        </button>

        <button
          onClick={() => setActiveTab("redirects")}
          className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition ${
            activeTab === "redirects"
              ? "border-sky-500 text-sky-400 bg-slate-800/40"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          <ArrowRight className="w-4 h-4" />
          <span>Redirects & Versions</span>
        </button>
      </div>

      {/* TAB 1: URL Health Dashboard */}
      {activeTab === "health" && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search URL in health observations..."
                value={healthSearch}
                onChange={(e) => setHealthSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadHealthData()}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
              />
            </div>

            <div className="flex items-center gap-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={healthStatusFilter}
                onChange={(e) => setHealthStatusFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none"
              >
                <option value="ALL">All Statuses</option>
                <option value="HEALTHY">Healthy (200)</option>
                <option value="FAILING">Failing / Under Verification</option>
                <option value="404">HTTP 404</option>
                <option value="301">HTTP 301 Redirect</option>
              </select>
              <button
                onClick={loadHealthData}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg flex items-center gap-1"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingHealth ? "animate-spin" : ""}`} />
                <span>Search</span>
              </button>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            {healthItems.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                {loadingHealth ? "Loading health observations..." : "No URL health observations match current query."}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3">Canonical URL</th>
                      <th className="p-3">HTTP Status</th>
                      <th className="p-3">Failures (X Thresh)</th>
                      <th className="p-3">Pending Action</th>
                      <th className="p-3">Sitemap Presence</th>
                      <th className="p-3">Last Verified</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70 font-mono text-[11px]">
                    {healthItems.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/30 transition">
                        <td className="p-3 max-w-xs truncate" title={item.canonical_url || item.url}>
                          <span className="text-slate-200 block truncate">{item.canonical_url || item.url}</span>
                          {item.redirect_destination_url && (
                            <span className="text-[10px] text-amber-400 flex items-center gap-1 font-sans">
                              <ArrowRight className="w-3 h-3" /> Redirects to: {item.redirect_destination_url}
                            </span>
                          )}
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-1.5 py-0.5 rounded font-bold ${
                              item.current_http_status === 200
                                ? "text-emerald-400 bg-emerald-950/60 border border-emerald-800"
                                : item.current_http_status === 301
                                ? "text-amber-400 bg-amber-950/60 border border-amber-800"
                                : "text-rose-400 bg-rose-950/60 border border-rose-800"
                            }`}
                          >
                            {item.current_http_status || "N/A"}
                          </span>
                        </td>
                        <td className="p-3 text-slate-300 font-sans">
                          <strong className={item.consecutive_failures > 0 ? "text-rose-400" : "text-slate-300"}>
                            {item.consecutive_failures}
                          </strong>{" "}
                          / {item.failure_threshold_x}
                        </td>
                        <td className="p-3 font-sans">
                          {item.pending_action ? (
                            <span className="text-[10px] bg-rose-950/70 text-rose-300 border border-rose-800 px-2 py-0.5 rounded uppercase font-bold">
                              {item.pending_action}
                            </span>
                          ) : item.consecutive_failures > 0 ? (
                            <span className="text-[10px] bg-amber-950/70 text-amber-300 border border-amber-800 px-2 py-0.5 rounded uppercase font-medium">
                              Pending Verification
                            </span>
                          ) : (
                            <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" /> Healthy
                            </span>
                          )}
                        </td>
                        <td className="p-3 font-sans">
                          {item.in_sitemap ? (
                            <span className="text-slate-300">Present</span>
                          ) : (
                            <span className="text-rose-400 font-semibold">Missing from sitemap</span>
                          )}
                        </td>
                        <td className="p-3 text-slate-400 text-[10px]">
                          {item.last_attempted_fetch_at ? new Date(item.last_attempted_fetch_at).toLocaleString() : "—"}
                        </td>
                        <td className="p-3 text-right font-sans">
                          <div className="flex items-center justify-end gap-1.5">
                            {item.pending_action && (
                              <button
                                onClick={() => handleCancelPending(item.url)}
                                className="px-2 py-1 bg-amber-950 hover:bg-amber-900 text-amber-200 border border-amber-800 rounded text-[11px]"
                                title="Cancel pending quarantine and reset failure count"
                              >
                                Cancel
                              </button>
                            )}
                            <button
                              onClick={() => handleReverifyUrl(item.url)}
                              className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 rounded text-[11px] border border-slate-700"
                              title="Immediately fetch and verify this URL live"
                            >
                              Re-verify
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: Archived Knowledge Base */}
      {activeTab === "archive" && (
        <div className="space-y-4">
          <div className="p-4 bg-slate-900 border border-slate-800 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-3">
              <Archive className="w-5 h-5 text-sky-400 shrink-0" />
              <div>
                <strong className="text-slate-100 block">Isolated Historical Knowledge Base</strong>
                <span className="text-slate-400">
                  Preserved articles, chunks and embedding references are securely isolated from active RAG answers.
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-slate-400">Retention Preset:</span>
              <select
                defaultValue="30_days"
                onChange={(e) => {
                  const preset = e.target.value;
                  archiveItems.forEach(item => handleUpdateRetention(item.id, preset));
                }}
                className="bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200"
              >
                <option value="2_days">2 Days Preset</option>
                <option value="15_days">15 Days Preset</option>
                <option value="30_days">30 Days Preset</option>
              </select>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search archived articles or URLs..."
                value={archiveSearch}
                onChange={(e) => setArchiveSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadArchiveData()}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
              />
            </div>

            <div className="flex items-center gap-2 text-xs">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={archiveReasonFilter}
                onChange={(e) => setArchiveReasonFilter(e.target.value)}
                className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none"
              >
                <option value="ALL">All Reasons</option>
                <option value="HTTP_404_CONFIRMED">HTTP 404 Confirmed</option>
                <option value="PERMANENT_REDIRECT_301">301 Permanent Redirect</option>
                <option value="MANUAL_ARCHIVE">Manual Archive</option>
              </select>
              <button
                onClick={loadArchiveData}
                className="px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg flex items-center gap-1"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingArchive ? "animate-spin" : ""}`} />
                <span>Filter</span>
              </button>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            {archiveItems.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                {loadingArchive ? "Loading archive..." : "No archived articles found."}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3">Title & Canonical URL</th>
                      <th className="p-3">Archive Reason</th>
                      <th className="p-3">Retention Policy</th>
                      <th className="p-3">Archive Date</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70 text-[11px]">
                    {archiveItems.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-800/30 transition">
                        <td className="p-3 max-w-sm">
                          <strong className="text-slate-100 block truncate">{item.title}</strong>
                          <span className="text-[10px] text-slate-400 font-mono block truncate" title={item.original_url}>
                            {item.original_url}
                          </span>
                          {item.replacement_url && (
                            <span className="text-[10px] text-sky-400 flex items-center gap-1 mt-0.5">
                              <ArrowRight className="w-3 h-3" /> Replaced by: {item.replacement_url}
                            </span>
                          )}
                        </td>
                        <td className="p-3">
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800">
                            {item.archive_reason}
                          </span>
                        </td>
                        <td className="p-3 font-mono text-slate-300">
                          {item.retention_preset} ({item.retention_days} days)
                        </td>
                        <td className="p-3 text-slate-400">
                          {new Date(item.archived_at).toLocaleString()}
                        </td>
                        <td className="p-3 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleViewArchiveDetail(item.id)}
                              className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded text-xs border border-slate-700"
                            >
                              Preview
                            </button>
                            <button
                              onClick={() => handleRestoreArchive(item.id)}
                              className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-xs font-semibold flex items-center gap-1 shadow-sm"
                            >
                              <RotateCcw className="w-3 h-3" />
                              <span>Restore</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: Quarantine & 404s */}
      {activeTab === "quarantine" && (
        <div className="space-y-4">
          <div className="p-4 bg-amber-950/20 border border-amber-800/40 rounded-xl text-xs text-amber-200/90 flex items-start gap-3">
            <ShieldCheck className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold text-amber-300 block">Strict Zero Data Loss Invariant</span>
              Quarantined records retain full original text, chunk hashes, and embedding vectors. They are excluded from active retrieval but never deleted without human authorization.
            </div>
          </div>

          <div className="relative max-w-sm">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search quarantined URL or title..."
              value={quarantineSearch}
              onChange={(e) => setQuarantineSearch(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-200 focus:outline-none focus:border-amber-500/60"
            />
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            {quarantinedRecords.length === 0 ? (
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
                    {quarantinedRecords
                      .filter((rec) => {
                        if (!quarantineSearch.trim()) return true;
                        const q = quarantineSearch.toLowerCase();
                        return rec.url.toLowerCase().includes(q) || rec.title.toLowerCase().includes(q);
                      })
                      .map((rec) => (
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
                              onClick={() => handleRestoreQuarantine(rec.article_id)}
                              disabled={restoringId === rec.article_id}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm transition disabled:opacity-50 ml-auto"
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
      )}

      {/* TAB 4: Redirects & Version History */}
      {activeTab === "redirects" && (
        <div className="space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                Permanent 301 Redirect Mappings & Replacements ({redirects.length})
              </h2>
              <button onClick={loadRedirectsData} className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1">
                <RefreshCw className={`w-3.5 h-3.5 ${loadingRedirects ? "animate-spin" : ""}`} />
                <span>Refresh</span>
              </button>
            </div>

            {redirects.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                No 301 redirect mappings recorded yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono text-[11px]">
                  <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3">Source URL</th>
                      <th className="p-3">Destination URL</th>
                      <th className="p-3">Hops</th>
                      <th className="p-3">Replacement Indexed</th>
                      <th className="p-3">Detected At</th>
                      <th className="p-3 text-right">History</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/70">
                    {redirects.map((r) => (
                      <tr key={r.id} className="hover:bg-slate-800/30 transition">
                        <td className="p-3 max-w-xs truncate text-slate-300" title={r.source_url}>{r.source_url}</td>
                        <td className="p-3 max-w-xs truncate text-sky-400" title={r.destination_url}>{r.destination_url}</td>
                        <td className="p-3 text-slate-400">{r.hop_count} hops</td>
                        <td className="p-3 font-sans">
                          {r.replacement_indexed ? (
                            <span className="text-emerald-400 font-bold flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" /> Indexed
                            </span>
                          ) : (
                            <span className="text-amber-400 font-medium">Pending Indexing</span>
                          )}
                        </td>
                        <td className="p-3 text-slate-400 font-sans text-[10px]">
                          {new Date(r.detected_at).toLocaleString()}
                        </td>
                        <td className="p-3 text-right font-sans">
                          <button
                            onClick={() => handleViewHistory(r.source_url)}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-sky-400 rounded text-xs border border-slate-700"
                          >
                            Version History
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
      )}

      {/* Archive Detail & Content Preview Modal */}
      {selectedArchiveDetail && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-3xl w-full max-h-[85vh] flex flex-col space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Archive className="w-4 h-4 text-sky-400" />
                  <span>Archived Document Preview</span>
                </h3>
                <span className="text-[11px] text-slate-400 font-mono truncate block max-w-xl">
                  {selectedArchiveDetail.original_url}
                </span>
              </div>
              <button onClick={() => setSelectedArchiveDetail(null)} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs bg-slate-950 p-3 rounded-lg border border-slate-800">
              <div>
                <span className="text-slate-400 text-[10px] block">Reason:</span>
                <strong className="text-sky-300">{selectedArchiveDetail.archive_reason}</strong>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Archived Date:</span>
                <span className="text-slate-200">{new Date(selectedArchiveDetail.archived_at).toLocaleDateString()}</span>
              </div>
              <div>
                <span className="text-slate-400 text-[10px] block">Retention Policy:</span>
                <span className="text-slate-200 font-mono">{selectedArchiveDetail.retention_preset} ({selectedArchiveDetail.retention_days}d)</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto bg-slate-950 border border-slate-800 rounded-xl p-4 text-xs font-mono text-slate-300 whitespace-pre-wrap leading-relaxed">
              {selectedArchiveDetail.full_content || "No content preserved."}
            </div>

            <div className="flex items-center justify-between border-t border-slate-800 pt-3">
              <button
                onClick={() => handleViewHistory(selectedArchiveDetail.original_url)}
                className="px-3 py-1.5 text-xs text-sky-400 hover:bg-slate-800 rounded-lg border border-slate-700 flex items-center gap-1.5"
              >
                <History className="w-3.5 h-3.5" />
                <span>View Full Version History</span>
              </button>

              <div className="flex gap-2">
                <button
                  onClick={() => setSelectedArchiveDetail(null)}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 rounded-lg"
                >
                  Close
                </button>
                <button
                  onClick={() => handleRestoreArchive(selectedArchiveDetail.id)}
                  className="px-4 py-2 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg flex items-center gap-1.5 shadow-md shadow-emerald-600/20"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Restore Document to Active Knowledge</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {historyUrl && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-2xl w-full max-h-[85vh] flex flex-col space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <History className="w-4 h-4 text-sky-400" />
                  <span>Article Version History</span>
                </h3>
                <span className="text-[11px] text-slate-400 font-mono truncate block max-w-lg">
                  {historyUrl}
                </span>
              </div>
              <button onClick={() => { setHistoryUrl(null); setSelectedDiff(null); }} className="text-slate-400 hover:text-slate-200">
                <X className="w-4 h-4" />
              </button>
            </div>

            {loadingVersions ? (
              <div className="p-8 text-center text-slate-400 text-xs">Loading version tree...</div>
            ) : versionItems.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs">No prior versions recorded for this document.</div>
            ) : (
              <div className="space-y-3 flex-1 overflow-y-auto">
                {versionItems.map((v, idx) => (
                  <div key={v.id} className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-xs space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">Version #{versionItems.length - idx}: {v.change_classification || "CONTENT_UPDATE"}</span>
                      <span className="text-slate-400 text-[10px] font-mono">{new Date(v.changed_at).toLocaleString()}</span>
                    </div>
                    <div className="text-[11px] text-slate-400 font-mono flex items-center gap-2">
                      <span>Old hash: {v.previous_content_hash.substring(0, 10)}...</span>
                      <span>→</span>
                      <span>New hash: {v.new_content_hash.substring(0, 10)}...</span>
                    </div>
                    {idx < versionItems.length - 1 && (
                      <button
                        onClick={() => handleViewDiff(versionItems[idx + 1].id, v.id)}
                        className="text-[11px] text-sky-400 hover:underline flex items-center gap-1 font-sans"
                      >
                        Compare diff with previous version
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {selectedDiff && (
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg max-h-48 overflow-y-auto text-xs font-mono text-emerald-400 whitespace-pre-wrap">
                {selectedDiff}
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => { setHistoryUrl(null); setSelectedDiff(null); }}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
