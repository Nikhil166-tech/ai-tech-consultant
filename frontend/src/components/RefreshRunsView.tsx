import React, { useState } from "react";
import { RefreshRunSummary, RefreshRunUrlItem } from "../types";
import {
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Search,
  Filter,
  Calendar,
  Layers
} from "lucide-react";

interface RefreshRunsViewProps {
  runs: RefreshRunSummary[];
  onFetchRunDetails: (runId: string) => Promise<{ summary: RefreshRunSummary; urls: RefreshRunUrlItem[] }>;
}

export const RefreshRunsView: React.FC<RefreshRunsViewProps> = ({ runs, onFetchRunDetails }) => {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(runs[0]?.id || null);
  const [selectedRunUrls, setSelectedRunUrls] = useState<RefreshRunUrlItem[]>([]);
  const [isLoadingUrls, setIsLoadingUrls] = useState(false);
  const [urlSearch, setUrlSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [isUrlPanelExpanded, setIsUrlPanelExpanded] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 25;

  const selectedRun = runs.find((r) => r.id === selectedRunId) || runs[0];

  const handleSelectRun = async (runId: string) => {
    setSelectedRunId(runId);
    setCurrentPage(1);
    setIsLoadingUrls(true);
    try {
      const data = await onFetchRunDetails(runId);
      setSelectedRunUrls(data.urls);
    } catch {
      setSelectedRunUrls([]);
    } finally {
      setIsLoadingUrls(false);
    }
  };

  React.useEffect(() => {
    if (runs[0]?.id && !selectedRunId) {
      handleSelectRun(runs[0].id);
    } else if (selectedRunId) {
      handleSelectRun(selectedRunId);
    }
  }, [runs.length]);

  // Filtering URLs
  const filteredUrls = selectedRunUrls.filter((item) => {
    if (statusFilter !== "ALL") {
      if (statusFilter === "CHANGED" && !item.content_changed) return false;
      if (statusFilter === "UNCHANGED" && item.action_taken !== "UNCHANGED") return false;
      if (statusFilter === "FAILED" && (!item.http_status || item.http_status >= 400)) return false;
    }
    if (urlSearch.trim()) {
      return item.url.toLowerCase().includes(urlSearch.toLowerCase());
    }
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filteredUrls.length / pageSize));
  const paginatedUrls = filteredUrls.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6">
      {/* Title */}
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
          <RefreshCw className="w-5 h-5 text-sky-400" />
          <span>Scheduled Refresh Runs</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          Review crawl lifecycle executions, content-hash diffs, HTTP statuses, and non-destructive quarantine transitions.
        </p>
      </div>

      {runs.length === 0 ? (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-12 text-center text-slate-500 text-xs">
          No refresh runs recorded yet. Add a sitemap to initiate automated refresh runs.
        </div>
      ) : (
        <div className="space-y-6">
          {/* Recent Runs Selector Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {runs.slice(0, 3).map((run) => {
              const isSelected = run.id === selectedRun?.id;
              return (
                <button
                  key={run.id}
                  onClick={() => handleSelectRun(run.id)}
                  className={`text-left p-4 rounded-xl border transition flex flex-col justify-between ${
                    isSelected
                      ? "bg-slate-900 border-sky-500/80 shadow-lg shadow-sky-500/10"
                      : "bg-slate-950/60 border-slate-800 hover:bg-slate-900/50"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs w-full">
                    <span className="font-bold text-slate-200">Run: {new Date(run.started_at).toLocaleDateString()}</span>
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                        run.status === "COMPLETED"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          : "bg-sky-950 text-sky-300 border border-sky-800"
                      }`}
                    >
                      {run.status}
                    </span>
                  </div>

                  <div className="text-[11px] text-slate-400 mt-2 space-y-0.5">
                    <div>Fetched: <strong className="text-slate-100">{run.total_fetched_urls}</strong> of {run.total_discovered_urls}</div>
                    <div className="text-[10px] text-slate-500 font-mono">Started: {new Date(run.started_at).toLocaleTimeString()}</div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Selected Run Summary Details */}
          {selectedRun && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6 shadow-xl">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800 pb-4 gap-2">
                <div>
                  <h2 className="text-sm font-bold text-slate-100">Refresh Run Summary</h2>
                  <span className="text-[11px] text-slate-400 font-mono">{selectedRun.id}</span>
                </div>
                <div className="text-xs text-slate-400 flex items-center gap-4">
                  <span>Completed: <strong className="text-slate-200">{selectedRun.completed_at ? new Date(selectedRun.completed_at).toLocaleTimeString() : "In Progress"}</strong></span>
                </div>
              </div>

              {/* Execution Timestamps Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div className="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block">Job Start Time</span>
                  <span className="text-slate-200 font-mono">{new Date(selectedRun.started_at).toLocaleTimeString()}</span>
                </div>
                <div className="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block">First URL Fetch</span>
                  <span className="text-slate-200 font-mono">
                    {selectedRun.first_successful_fetch_at ? new Date(selectedRun.first_successful_fetch_at).toLocaleTimeString() : "—"}
                  </span>
                </div>
                <div className="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block">Last URL Fetch</span>
                  <span className="text-slate-200 font-mono">
                    {selectedRun.last_successful_fetch_at ? new Date(selectedRun.last_successful_fetch_at).toLocaleTimeString() : "—"}
                  </span>
                </div>
                <div className="p-3 bg-slate-950/70 border border-slate-800/80 rounded-lg">
                  <span className="text-slate-400 text-[10px] uppercase font-bold block">Completion Time</span>
                  <span className="text-slate-200 font-mono">
                    {selectedRun.completed_at ? new Date(selectedRun.completed_at).toLocaleTimeString() : "Running"}
                  </span>
                </div>
              </div>

              {/* Inventory Metrics Count */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 text-center">
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                  <span className="text-slate-400 text-[10px] block">Added</span>
                  <strong className="text-emerald-400 text-lg">{selectedRun.added_count}</strong>
                </div>
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                  <span className="text-slate-400 text-[10px] block">Updated</span>
                  <strong className="text-sky-400 text-lg">{selectedRun.updated_count}</strong>
                </div>
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                  <span className="text-slate-400 text-[10px] block">Unchanged</span>
                  <strong className="text-slate-300 text-lg">{selectedRun.unchanged_count}</strong>
                </div>
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                  <span className="text-slate-400 text-[10px] block">Failed</span>
                  <strong className="text-rose-400 text-lg">{selectedRun.failed_count}</strong>
                </div>
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                  <span className="text-slate-400 text-[10px] block">Pending</span>
                  <strong className="text-amber-400 text-lg">{selectedRun.pending_count}</strong>
                </div>
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                  <span className="text-slate-400 text-[10px] block">Quarantined</span>
                  <strong className="text-purple-400 text-lg">{selectedRun.quarantined_count}</strong>
                </div>
              </div>

              {/* Expandable Panel: Complete URL Inventory Listing */}
              <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950">
                <button
                  onClick={() => setIsUrlPanelExpanded(!isUrlPanelExpanded)}
                  className="w-full p-4 bg-slate-900/70 border-b border-slate-800 flex items-center justify-between text-xs font-bold text-slate-200"
                >
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-sky-400" />
                    <span>Complete URL Inventory Details ({selectedRunUrls.length} pages)</span>
                  </div>
                  {isUrlPanelExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>

                {isUrlPanelExpanded && (
                  <div className="p-4 space-y-4">
                    {/* Search and Filters */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="relative flex-1 max-w-sm">
                        <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
                        <input
                          type="text"
                          placeholder="Filter URLs in this run..."
                          value={urlSearch}
                          onChange={(e) => setUrlSearch(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
                        />
                      </div>

                      <div className="flex items-center gap-2 text-xs">
                        <Filter className="w-3.5 h-3.5 text-slate-400" />
                        <select
                          value={statusFilter}
                          onChange={(e) => setStatusFilter(e.target.value)}
                          className="bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none"
                        >
                          <option value="ALL">All Statuses</option>
                          <option value="CHANGED">Changed Only</option>
                          <option value="UNCHANGED">Unchanged Only</option>
                          <option value="FAILED">Failed Only</option>
                        </select>
                      </div>
                    </div>

                    {/* URLs Table */}
                    <div className="overflow-x-auto max-h-96 overflow-y-auto border border-slate-800/80 rounded-lg">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-900/90 text-slate-400 sticky top-0 border-b border-slate-800">
                          <tr>
                            <th className="p-2.5">URL</th>
                            <th className="p-2.5">HTTP Status</th>
                            <th className="p-2.5">Action Taken</th>
                            <th className="p-2.5">Hash Diff</th>
                            <th className="p-2.5">Sitemap lastmod</th>
                            <th className="p-2.5">Fetch Timestamp</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                          {filteredUrls.length === 0 ? (
                            <tr>
                              <td colSpan={6} className="p-4 text-center text-slate-500 font-sans">
                                No URLs match current filters.
                              </td>
                            </tr>
                          ) : (
                            paginatedUrls.map((u, idx) => (
                              <tr key={idx} className="hover:bg-slate-900/40">
                                <td className="p-2.5 text-slate-200 max-w-xs truncate" title={u.url}>{u.url}</td>
                                <td className="p-2.5">
                                  <span
                                    className={`px-1.5 py-0.5 rounded font-bold ${
                                      u.http_status === 200
                                        ? "text-emerald-400 bg-emerald-950/60"
                                        : u.http_status && u.http_status < 400
                                        ? "text-sky-400 bg-sky-950/60"
                                        : "text-rose-400 bg-rose-950/60"
                                    }`}
                                  >
                                    {u.http_status || "N/A"}
                                  </span>
                                </td>
                                <td className="p-2.5 text-slate-300 font-sans">{u.action_taken}</td>
                                <td className="p-2.5">
                                  {u.content_changed ? (
                                    <span className="text-amber-400 font-sans font-semibold">MODIFIED</span>
                                  ) : (
                                    <span className="text-slate-500 font-sans">Same</span>
                                  )}
                                </td>
                                <td className="p-2.5 text-slate-400">{u.sitemap_lastmod || "—"}</td>
                                <td className="p-2.5 text-slate-400">
                                  {u.fetched_at ? new Date(u.fetched_at).toLocaleTimeString() : "—"}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>

                    {/* Pagination Controls */}
                    {totalPages > 1 && (
                      <div className="flex items-center justify-between text-xs pt-1">
                        <span className="text-slate-400">
                          Showing {(currentPage - 1) * pageSize + 1} - {Math.min(currentPage * pageSize, filteredUrls.length)} of {filteredUrls.length} URLs
                        </span>
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage === 1}
                            className="px-2.5 py-1 bg-slate-900 border border-slate-800 rounded text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                          >
                            Previous
                          </button>
                          <span className="text-slate-400 px-2">Page {currentPage} of {totalPages}</span>
                          <button
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                            disabled={currentPage === totalPages}
                            className="px-2.5 py-1 bg-slate-900 border border-slate-800 rounded text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Bottom Total Fetched URL Count */}
                    <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg flex items-center justify-between text-xs">
                      <span className="text-slate-400">Total Successfully Fetched URLs in this Run:</span>
                      <strong className="text-sky-400 font-mono text-sm">{selectedRun.total_fetched_urls} URLs</strong>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
