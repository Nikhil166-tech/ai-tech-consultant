import React, { useState } from "react";
import { TaxonomyItem, GmailAccountStatus, User } from "../types";
import {
  Settings,
  Mail,
  ShieldAlert,
  Tag,
  Plus,
  Trash2,
  CheckCircle2,
  Globe,
  Sliders,
  ExternalLink,
  LogOut,
  User as UserIcon
} from "lucide-react";

interface SettingsViewProps {
  user: User | null;
  gmailStatus: GmailAccountStatus;
  taxonomy: TaxonomyItem[];
  autonomySettings: any;
  userSettings: any;
  onUpdateAutonomySettings: (settings: any) => Promise<void>;
  onUpdateUserSettings: (settings: any) => Promise<void>;
  onUpdateTaxonomy: (items: TaxonomyItem[]) => Promise<void>;
  onConnectRealGmail: () => Promise<void>;
  onConnectMockGmail: () => Promise<void>;
  onDisconnectGmail: () => Promise<void>;
  onLogout: () => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  user,
  gmailStatus,
  taxonomy,
  autonomySettings,
  userSettings,
  onUpdateAutonomySettings,
  onUpdateUserSettings,
  onUpdateTaxonomy,
  onConnectRealGmail,
  onConnectMockGmail,
  onDisconnectGmail,
  onLogout
}) => {
  const [activeTab, setActiveTab] = useState<"general" | "taxonomy" | "gmail" | "quarantine">("general");

  const [defaultThreshold, setDefaultThreshold] = useState<number>(autonomySettings?.defaultThreshold || 3);
  const [requireGmail, setRequireGmail] = useState<boolean>(autonomySettings?.requireGmailConnection || false);
  const [minEvidenceScore, setMinEvidenceScore] = useState<number>(autonomySettings?.minEvidenceScore || 0.4);

  // Quarantine settings
  const [quarantineThreshold, setQuarantineThreshold] = useState<number>(
    userSettings?.url_verification_threshold || 3
  );
  const [refreshFrequency, setRefreshFrequency] = useState<string>(
    userSettings?.sitemap_refresh_frequency || "daily"
  );
  const [quarantineActionRule, setQuarantineActionRule] = useState<string>(
    userSettings?.quarantine_action_rule || "QUARANTINE_ON_CONSECUTIVE_FAILURES"
  );

  // Taxonomy item creation state
  const [newParentType, setNewParentType] = useState("Design Settings");
  const [newLabel, setNewLabel] = useState("");
  const [newKeywords, setNewKeywords] = useState("");
  const [newSynonyms, setNewSynonyms] = useState("");
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSaveAutonomySettings = async () => {
    await onUpdateAutonomySettings({
      defaultThreshold: Number(defaultThreshold),
      requireGmailConnection: requireGmail,
      minEvidenceScore: Number(minEvidenceScore)
    });
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  const handleSaveQuarantineSettings = async () => {
    await onUpdateUserSettings({
      url_verification_threshold: Number(quarantineThreshold),
      sitemap_refresh_frequency: refreshFrequency,
      quarantine_action_rule: quarantineActionRule
    });
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  const handleAddTaxonomy = async () => {
    if (!newLabel.trim()) return;
    const newItem: TaxonomyItem = {
      id: `tax_${Date.now()}`,
      parentSettingType: newParentType,
      specificLabel: newLabel.trim(),
      description: `Custom ${newLabel.trim()} taxonomy item`,
      keywords: newKeywords.split(",").map((k) => k.trim()).filter(Boolean),
      synonyms: newSynonyms.split(",").map((s) => s.trim()).filter(Boolean),
      enabled: true
    };
    const updated = [...taxonomy, newItem];
    await onUpdateTaxonomy(updated);
    setNewLabel("");
    setNewKeywords("");
    setNewSynonyms("");
  };

  const handleDeleteTaxonomy = async (id: string) => {
    const updated = taxonomy.filter((t) => t.id !== id);
    await onUpdateTaxonomy(updated);
  };

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-6">
      {/* Title */}
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
            <Settings className="w-5 h-5 text-sky-400" />
            <span>Platform Configuration & Settings</span>
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Configure sitemap refresh intervals, quarantine thresholds, email classification taxonomy, and Gmail OAuth.
          </p>
        </div>

        {savedSuccess && (
          <span className="flex items-center gap-1 text-xs text-emerald-400 bg-emerald-950/60 border border-emerald-800 px-3 py-1 rounded-lg">
            <CheckCircle2 className="w-3.5 h-3.5" />
            Saved successfully!
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-800 pb-2 overflow-x-auto">
        <button
          onClick={() => setActiveTab("general")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition shrink-0 ${activeTab === "general" ? "bg-sky-600 text-white" : "text-slate-400 hover:bg-slate-800"
            }`}
        >
          Autonomy & Auto-Send
        </button>
        <button
          onClick={() => setActiveTab("quarantine")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition shrink-0 ${activeTab === "quarantine" ? "bg-sky-600 text-white" : "text-slate-400 hover:bg-slate-800"
            }`}
        >
          Sitemaps & Quarantine
        </button>
        <button
          onClick={() => setActiveTab("taxonomy")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition shrink-0 ${activeTab === "taxonomy" ? "bg-sky-600 text-white" : "text-slate-400 hover:bg-slate-800"
            }`}
        >
          Classification Taxonomy
        </button>
        <button
          onClick={() => setActiveTab("gmail")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition shrink-0 ${activeTab === "gmail" ? "bg-sky-600 text-white" : "text-slate-400 hover:bg-slate-800"
            }`}
        >
          Gmail OAuth Integration
        </button>
      </div>




      {/* Tab: Autonomy & Auto-Send Settings */}
      {activeTab === "general" && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
          <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Sliders className="w-4 h-4 text-sky-400" />
            <span>Configurable Auto-Send Policy (Phase 11)</span>
          </h2>

          <div className="space-y-4 max-w-xl text-xs">
            <div>
              <label className="text-slate-200 font-semibold block mb-1">
                Default Approval Threshold X (Per-Label)
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={defaultThreshold}
                onChange={(e) => setDefaultThreshold(parseInt(e.target.value, 10) || 1)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100 font-mono"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Number of consecutive unchanged human approvals required for a specific label before auto-send activates.
              </span>
            </div>

            <div>
              <label className="text-slate-200 font-semibold block mb-1">
                Minimum Knowledge Brain Evidence Score
              </label>
              <input
                type="number"
                step="0.05"
                min="0"
                max="1"
                value={minEvidenceScore}
                onChange={(e) => setMinEvidenceScore(parseFloat(e.target.value) || 0)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100 font-mono"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Drafts with evidence score below this threshold are blocked from automated delivery.
              </span>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <input
                type="checkbox"
                id="requireGmail"
                checked={requireGmail}
                onChange={(e) => setRequireGmail(e.target.checked)}
                className="rounded bg-slate-950 border-slate-800 text-sky-500 focus:ring-0"
              />
              <label htmlFor="requireGmail" className="text-slate-300 font-medium cursor-pointer">
                Require Active Gmail Connection for Automated Sending
              </label>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800 flex justify-end">
            <button
              onClick={handleSaveAutonomySettings}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-md"
            >
              Save Autonomy Settings
            </button>
          </div>
        </div>
      )}

      {/* Tab: Sitemaps & Quarantine Settings */}
      {activeTab === "quarantine" && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
          <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <Globe className="w-4 h-4 text-sky-400" />
            <span>Sitemaps & Quarantine Rules (Phase 3 & 4)</span>
          </h2>

          <div className="space-y-4 max-w-xl text-xs">
            <div>
              <label className="text-slate-200 font-semibold block mb-1">Sitemap Refresh Frequency</label>
              <select
                value={refreshFrequency}
                onChange={(e) => setRefreshFrequency(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100"
              >
                <option value="daily">Every day</option>
                <option value="weekly">Every week</option>
                <option value="15_days">Every 15 days</option>
                <option value="30_days">Every 30 days</option>
              </select>
            </div>

            <div>
              <label className="text-slate-200 font-semibold block mb-1">
                URL Verification Threshold X (Consecutive Scheduled Checks)
              </label>
              <input
                type="number"
                min={1}
                max={10}
                value={quarantineThreshold}
                onChange={(e) => setQuarantineThreshold(parseInt(e.target.value, 10) || 1)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-100 font-mono"
              />
              <span className="text-[11px] text-slate-400 mt-1 block">
                Approved Option A rule: Requires a URL to fail across X consecutive scheduled refresh runs before triggering quarantine.
              </span>
            </div>

            <div>
              <label className="text-slate-200 font-semibold block mb-1">Missing-Page Quarantine Action Rule</label>
              <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-slate-300 space-y-1">
                <span className="font-semibold text-emerald-400 block">Option 1 Active (Strict Invariant)</span>
                <span className="text-[11px] text-slate-400 block">
                  A URL must return HTTP 404 AND be absent from the latest sitemap to qualify for missing-page quarantine. Temporary network glitches never quarantine knowledge.
                </span>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800 flex justify-end">
            <button
              onClick={handleSaveQuarantineSettings}
              className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-md"
            >
              Save Quarantine Settings
            </button>
          </div>
        </div>
      )}

      {/* Tab: Classification Taxonomy Manager */}
      {activeTab === "taxonomy" && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <Tag className="w-4 h-4 text-sky-400" />
                <span>Email Classification Taxonomy Manager (Phase 9)</span>
              </h2>
              <p className="text-[11px] text-slate-400">
                Define and manage parent setting types, specific labels, keywords, and synonym recognition.
              </p>
            </div>
          </div>

          {/* Add New Taxonomy Item */}
          <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3 text-xs">
            <span className="font-bold text-slate-200 block">Add New Label & Synonyms</span>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-slate-400 block mb-1">Parent Setting Type</label>
                <select
                  value={newParentType}
                  onChange={(e) => setNewParentType(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-slate-200"
                >
                  <option value="Design Settings">Design Settings</option>
                  <option value="Menu Manager">Menu Manager</option>
                  <option value="Billing">Billing</option>
                  <option value="Filters">Filters</option>
                  <option value="Domain Management">Domain Management</option>
                  <option value="Staging">Staging</option>
                  <option value="General Settings">General Settings</option>
                </select>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Specific Label Name</label>
                <input
                  type="text"
                  placeholder="e.g. Header, Footer, DNS..."
                  value={newLabel}
                  onChange={(e) => setNewLabel(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-slate-200"
                />
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Keywords (comma-separated)</label>
                <input
                  type="text"
                  placeholder="e.g. header, logo, masthead"
                  value={newKeywords}
                  onChange={(e) => setNewKeywords(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-slate-200"
                />
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Synonyms (comma-separated)</label>
                <input
                  type="text"
                  placeholder="e.g. top banner, site title"
                  value={newSynonyms}
                  onChange={(e) => setNewSynonyms(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg p-2 text-slate-200"
                />
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={handleAddTaxonomy}
                disabled={!newLabel.trim()}
                className="flex items-center gap-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold disabled:opacity-50"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Taxonomy Item</span>
              </button>
            </div>
          </div>

          {/* Taxonomy Items List */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-slate-300 block">Registered Taxonomy ({taxonomy.length})</span>
            <div className="divide-y divide-slate-800 border border-slate-800 rounded-xl overflow-hidden bg-slate-950">
              {taxonomy.map((t) => (
                <div key={t.id} className="p-3 flex items-center justify-between text-xs hover:bg-slate-900/40">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <strong className="text-slate-100">{t.parentSettingType} → {t.specificLabel}</strong>
                    </div>
                    <div className="text-[11px] text-slate-400">
                      Keywords: <span className="text-slate-300">{t.keywords.join(", ")}</span> | Synonyms: <span className="text-slate-300">{t.synonyms.join(", ")}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteTaxonomy(t.id)}
                    className="text-slate-500 hover:text-rose-400 p-1"
                    title="Delete item"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Tab: Gmail OAuth Integration */}
      {activeTab === "gmail" && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6">
          <div className="border-b border-slate-800 pb-3">
            <h2 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Mail className="w-4 h-4 text-sky-400" />
              <span>Real Gmail OAuth Integration (Phase 8)</span>
            </h2>
            <p className="text-[11px] text-slate-400">
              Connect ONE real Gmail account per user using Google's supported OAuth 2.0 flow and Gmail APIs.
            </p>
          </div>

          {/* Status Box */}
          <div className="p-4 bg-slate-950 border border-slate-800 rounded-xl flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-lg flex items-center justify-center ${gmailStatus.isConnected ? "bg-emerald-500/10 text-emerald-400" : "bg-slate-800 text-slate-500"
                  }`}
              >
                <Mail className="w-5 h-5" />
              </div>
              <div>
                <span className="text-xs font-bold text-slate-100 block">
                  {gmailStatus.isConnected ? `Connected: ${gmailStatus.email}` : "No Gmail Account Connected"}
                </span>
                <span className="text-[11px] text-slate-400">
                  {gmailStatus.isConnected
                    ? `Mode: ${gmailStatus.isMock ? "Mock Demonstration Account" : "Live Google OAuth API"}`
                    : "Connect via Google OAuth to fetch inbox threads and send approved customer emails."}
                </span>
              </div>
            </div>

            {gmailStatus.isConnected ? (
              <button
                onClick={onDisconnectGmail}
                className="px-3 py-1.5 bg-rose-950 border border-rose-800 text-rose-300 hover:bg-rose-900 rounded-lg text-xs font-semibold"
              >
                Disconnect
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={onConnectRealGmail}
                  className="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-600/20"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Connect Real Gmail</span>
                </button>
                <button
                  onClick={onConnectMockGmail}
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium border border-slate-700"
                  title="Connect offline mock account for testing without Google Cloud API credentials"
                >
                  Use Mock Account
                </button>
              </div>
            )}
          </div>

          <div className="text-xs text-slate-400 space-y-2">
            <h4 className="font-semibold text-slate-300">Required OAuth Credentials (.env)</h4>
            <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-[11px] space-y-1">
              <div>GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com</div>
              <div>GOOGLE_CLIENT_SECRET=your_client_secret</div>
              <div>GOOGLE_REDIRECT_URI=http://localhost:3000/api/v1/gmail/callback</div>
            </div>
            <p className="text-[11px] text-slate-500">
              When credentials are not provided, the system supports local mock testing so you can verify inbox and drafting workflows offline.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
