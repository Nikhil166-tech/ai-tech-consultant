import React, { useState } from "react";
import { SitemapItem, SitemapPreview, IndexingEstimate } from "../types";
import { Globe, Plus, Eye, Play, AlertCircle, Clock, CheckCircle2, ChevronRight, RefreshCw, Calendar, ExternalLink } from "lucide-react";

interface SitemapManagementViewProps {
  sitemaps: SitemapItem[];
  indexingEstimate: IndexingEstimate | null;
  onPreview: (url: string) => Promise<SitemapPreview>;
  onCreateAndIndex: (url: string, interval: string) => Promise<void>;
  onTriggerRefresh: (sitemapId: string) => Promise<void>;
  onRefreshData: () => void;
}

export const SitemapManagementView: React.FC<SitemapManagementViewProps> = ({
  sitemaps,
  indexingEstimate,
  onPreview,
  onCreateAndIndex,
  onTriggerRefresh,
  onRefreshData
}) => {
  const [showAddModal, setShowAddModal] = useState(false);
  const [sitemapUrl, setSitemapUrl] = useState("");
  const [refreshInterval, setRefreshInterval] = useState("daily");
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewData, setPreviewData] = useState<SitemapPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isConfirmingIndex, setIsConfirmingIndex] = useState(false);

  const handleFetchPreview = async () => {
    if (!sitemapUrl.trim()) return;
    setIsLoadingPreview(true);
    setPreviewError(null);
    setPreviewData(null);
    try {
      const data = await onPreview(sitemapUrl.trim());
      setPreviewData(data);
    } catch (err: any) {
      setPreviewError(err?.message || "Failed to preview sitemap");
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleConfirmAndAdd = async () => {
    if (!sitemapUrl.trim()) return;
    setIsConfirmingIndex(true);
    try {
      await onCreateAndIndex(sitemapUrl.trim(), refreshInterval);
      setShowAddModal(false);
      setSitemapUrl("");
      setPreviewData(null);
      onRefreshData();
    } catch (err: any) {
      setPreviewError(err?.message || "Failed to confirm indexing");
    } finally {
      setIsConfirmingIndex(false);
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2.5">
            <Globe className="w-5 h-5 text-sky-400" />
            <span>Sitemap Management</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Register and monitor XML sitemaps and nested indexes with zero data-loss crawl isolation.
          </p>
        </div>

        <button
          onClick={() => {
            setShowAddModal(true);
            setPreviewData(null);
            setPreviewError(null);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-lg text-xs font-semibold shadow-lg shadow-sky-500/20 transition"
        >
          <Plus className="w-4 h-4" />
          <span>Add New Sitemap</span>
        </button>
      </div>

      {/* Indexing Estimates Banner (5-minute rolling window) */}
      {indexingEstimate && (
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-100">Rolling Throughput & Completion Estimate</span>
                <span className="text-[10px] bg-amber-950 text-amber-300 border border-amber-800/60 px-2 py-0.2 rounded font-medium">
                  Estimate Only
                </span>
              </div>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Observed throughput: <strong className="text-slate-200">{indexingEstimate.observed_pages_per_5min} pages</strong> per 5-min window (~{indexingEstimate.estimated_pages_per_hour} pages/hr).
              </p>
            </div>
          </div>

          <div className="text-right">
            <span className="text-[11px] text-slate-400 block">Est. Completion Duration</span>
            <span className="text-sm font-bold font-mono text-sky-400">{indexingEstimate.formatted_estimate}</span>
          </div>
        </div>
      )}

      {/* Sitemaps List */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg shadow-black/20">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Registered Sitemaps ({sitemaps.length})</h2>
          <button onClick={onRefreshData} className="text-slate-400 hover:text-slate-200 text-xs flex items-center gap-1">
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>

        {sitemaps.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs space-y-2">
            <Globe className="w-8 h-8 mx-auto text-slate-600 mb-2" />
            <p className="font-medium text-slate-300">No sitemaps registered yet.</p>
            <p>Click "Add New Sitemap" to validate and preview your documentation inventory.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {sitemaps.map((sm) => (
              <div key={sm.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-800/30 transition">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <a
                      href={sm.url || sm.root_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-bold text-sky-400 hover:text-sky-300 hover:underline font-mono flex items-center gap-1.5"
                    >
                      <span>{sm.name || sm.url || sm.root_url}</span>
                      <ExternalLink className="w-3 h-3 text-slate-400" />
                    </a>
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${
                        (sm.status || "").toLowerCase() === "active" || (sm.status || "").toLowerCase() === "confirmed" || (sm.status || "").toLowerCase() === "valid"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                          : "bg-sky-950 text-sky-300 border border-sky-800/60"
                      }`}
                    >
                      {sm.status}
                    </span>
                    <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-medium flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-sky-400" />
                      {sm.refresh_interval || (sm.refresh_interval_days ? `${sm.refresh_interval_days}d` : "daily")}
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-400 font-mono block truncate max-w-lg">
                    {sm.url || sm.root_url}
                  </span>

                  <div className="flex items-center gap-4 text-xs text-slate-400">
                    <span>Discovered: <strong className="text-slate-200">{sm.discovered_sitemaps_count}</strong> sitemaps</span>
                    <span>•</span>
                    <span>Total URLs: <strong className="text-slate-200">{sm.total_urls_count}</strong></span>
                    <span>•</span>
                    <span>Last Validated: {sm.last_validated_at ? new Date(sm.last_validated_at).toLocaleDateString() : "Never"}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onTriggerRefresh(sm.id)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold border border-slate-700 transition"
                  >
                    <Play className="w-3.5 h-3.5 text-sky-400" />
                    <span>Run Refresh Now</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Sitemap Modal with Explicit Preview Confirmation */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-xl w-full space-y-5 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <Globe className="w-4 h-4 text-sky-400" />
                <span>Add & Validate Sitemap</span>
              </h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-slate-200 text-xs">
                ✕
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Sitemap or Sitemap Index URL</label>
                <div className="flex gap-2">
                  <input
                    type="url"
                    placeholder="https://support.brilliantdirectories.com/sitemap.xml"
                    value={sitemapUrl}
                    onChange={(e) => setSitemapUrl(e.target.value)}
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                  />
                  <button
                    onClick={handleFetchPreview}
                    disabled={isLoadingPreview || !sitemapUrl.trim()}
                    className="flex items-center gap-1 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold disabled:opacity-50"
                  >
                    <Eye className="w-3.5 h-3.5" />
                    <span>{isLoadingPreview ? "Validating..." : "Preview"}</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-300 block mb-1">Scheduled Refresh Interval</label>
                <select
                  value={refreshInterval}
                  onChange={(e) => setRefreshInterval(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
                >
                  <option value="daily">Every day</option>
                  <option value="weekly">Every week</option>
                  <option value="15_days">Every 15 days</option>
                  <option value="30_days">Every 30 days</option>
                </select>
              </div>
            </div>

            {/* Error Message */}
            {previewError && (
              <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-lg text-xs text-rose-300 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold">Validation Error:</span> {previewError}
                </div>
              </div>
            )}

            {/* Preview Results Panel */}
            {previewData && (
              <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-xs font-bold text-slate-200">Sitemap Inventory Preview</span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded uppercase ${
                      previewData.validation_status?.toLowerCase() === "valid"
                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                        : "bg-rose-950 text-rose-300 border border-rose-800"
                    }`}
                  >
                    {previewData.validation_status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-slate-400 block text-[11px]">Discovered Sitemaps</span>
                    <strong className="text-slate-100 text-sm">{previewData.discovered_sitemaps_count}</strong>
                    <span className="text-[10px] text-slate-500 block">({previewData.nested_sitemaps_count} nested)</span>
                  </div>
                  <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                    <span className="text-slate-400 block text-[11px]">Extracted URLs</span>
                    <strong className="text-slate-100 text-sm">{previewData.total_extracted_urls}</strong>
                    <span className="text-[10px] text-emerald-400 block">({previewData.total_unique_urls} unique)</span>
                  </div>
                </div>

                {/* First & Last URLs in Discovery Order with lastmod */}
                <div className="space-y-1.5 text-[11px]">
                  <div className="p-2 bg-slate-900/40 rounded border border-slate-800/80">
                    <span className="text-slate-400 block font-semibold">First URL in Discovery Order:</span>
                    <span className="text-slate-200 font-mono truncate block">{previewData.first_url || "None"}</span>
                    <span className="text-slate-400 text-[10px]">
                      lastmod: <strong className="text-slate-300">{previewData.first_url_lastmod || "Not specified by sitemap"}</strong>
                    </span>
                  </div>

                  <div className="p-2 bg-slate-900/40 rounded border border-slate-800/80">
                    <span className="text-slate-400 block font-semibold">Last URL in Discovery Order:</span>
                    <span className="text-slate-200 font-mono truncate block">{previewData.last_url || "None"}</span>
                    <span className="text-slate-400 text-[10px]">
                      lastmod: <strong className="text-slate-300">{previewData.last_url_lastmod || "Not specified by sitemap"}</strong>
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Modal Actions */}
            <div className="flex items-center justify-between pt-2 border-t border-slate-800">
              <span className="text-[11px] text-slate-500">
                Explicit confirmation is required before full indexing.
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowAddModal(false)}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmAndAdd}
                  disabled={
                    !previewData ||
                    previewData.can_index === false ||
                    previewData.validation_status?.toLowerCase() === "invalid" ||
                    isConfirmingIndex
                  }
                  className="px-4 py-2 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg disabled:opacity-50 flex items-center gap-1.5 shadow-md shadow-emerald-600/20"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{isConfirmingIndex ? "Indexing..." : "Confirm & Begin Indexing"}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
