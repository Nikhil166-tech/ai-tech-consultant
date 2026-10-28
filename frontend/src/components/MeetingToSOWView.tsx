import React, { useState, useEffect } from "react";
import {
  FileText,
  Sparkles,
  Plus,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Download,
  Printer,
  ChevronRight,
  ShieldCheck,
  RefreshCw,
  FolderOpen,
  Send,
  Users,
  Search,
  ExternalLink,
  GitBranch,
  Layers
} from "lucide-react";
import { ProjectScope, RequirementItem, ScopeChangeSet } from "../types";
import { api } from "../api";

interface MeetingToSOWViewProps {
  onRefreshData?: () => void;
}

export const MeetingToSOWView: React.FC<MeetingToSOWViewProps> = () => {
  const [projects, setProjects] = useState<ProjectScope[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"scope" | "follow_up" | "proposal">("scope");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // New Project Form Modal
  const [showNewModal, setShowNewModal] = useState(false);
  const [newProjectId, setNewProjectId] = useState("");
  const [newTranscript, setNewTranscript] = useState("");

  // Follow-up Meeting Form
  const [followUpTranscript, setFollowUpTranscript] = useState("");
  const [isProcessingFollowUp, setIsProcessingFollowUp] = useState(false);

  // Approval Form
  const [approverName, setApproverName] = useState("Lead Partner");
  const [isApproving, setIsApproving] = useState(false);

  const loadProjects = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const list = await api.listSOWProjects();
      setProjects(list || []);
      if (!selectedProjectId && list && list.length > 0) {
        setSelectedProjectId(list[0].project_id);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to load SOW projects");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const selectedProject = projects.find((p) => p.project_id === selectedProjectId) || null;

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTranscript.trim()) return;

    setLoading(true);
    setErrorMsg(null);
    try {
      const created = await api.createSOWFromMeeting(newTranscript.trim(), newProjectId.trim() || undefined);
      setSuccessMsg(`Project '${created.project_id}' created successfully from meeting transcript!`);
      setShowNewModal(false);
      setNewProjectId("");
      setNewTranscript("");
      await loadProjects();
      setSelectedProjectId(created.project_id);
      setActiveTab("scope");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to create SOW project");
    } finally {
      setLoading(false);
    }
  };

  const handleProcessFollowUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProject || !followUpTranscript.trim()) return;

    setIsProcessingFollowUp(true);
    setErrorMsg(null);
    try {
      const res = await api.processSOWFollowUp(selectedProject.project_id, followUpTranscript.trim());
      setSuccessMsg(
        `Follow-up meeting analyzed! Detected ${res.changes.added_requirements?.length || 0} new, ${
          res.changes.changed_requirements?.length || 0
        } changed requirements.`
      );
      setFollowUpTranscript("");
      await loadProjects();
      setActiveTab("scope");
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to process follow-up meeting");
    } finally {
      setIsProcessingFollowUp(false);
    }
  };

  const handleApproveSOW = async () => {
    if (!selectedProject || !approverName.trim()) return;

    setIsApproving(true);
    setErrorMsg(null);
    try {
      const approved = await api.approveSOWScope(selectedProject.project_id, approverName.trim());
      setSuccessMsg(`Statement of Work approved by ${approved.approved_by} and released for client delivery!`);
      await loadProjects();
      setActiveTab("proposal");
    } catch (err: any) {
      setErrorMsg(err.message || "Approval failed");
    } finally {
      setIsApproving(false);
    }
  };

  // Sample Meeting Transcripts for one-click testing
  const sampleTranscripts = [
    {
      title: "Initial Scope Meeting (Directory Staging & Payments)",
      content: `Client: Hi team, we need a complete migration to Brilliant Directories with automated Stripe recurring payments.
Agency: That sounds great. Are you looking to set up specific member pricing tiers and automatic renewal billing?
Client: Yes, monthly and annual member tiers with automatic Stripe billing and automated welcome email sequences upon signup.
Agency: Understood. What about your website header and branding?
Client: We need custom top navigation styling, our logo updated in the header, and custom CSS branding colors applied across all pages.`
    },
    {
      title: "Follow-up Meeting (Scope Evolution & CSV Export)",
      content: `Client: Following up on our last discussion, we also must have member data export to CSV format for our CRM.
Agency: Got it. Does Stripe payment processing and membership tiers remain unchanged?
Client: Keep Stripe payment processing unchanged. Leave member tiers as is. Just add the CSV member export functionality.`
    }
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] overflow-hidden bg-slate-950 text-slate-100">
      {/* Top Banner */}
      <div className="border-b border-slate-800 bg-slate-900/60 p-4 px-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500/20 to-sky-500/20 border border-indigo-500/30 text-indigo-400">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-100 flex items-center gap-2">
                <span>Meeting-to-SOW Autonomous Pipeline</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                  Task 3 Module
                </span>
              </h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Multi-agent pipeline: Requirements Extraction → Knowledge Brain Feasibility → Effort Estimation → Human-Approved SOW
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadProjects}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={() => setShowNewModal(true)}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white shadow-md shadow-sky-500/20 transition"
          >
            <Plus className="w-4 h-4" />
            <span>New SOW Project</span>
          </button>
        </div>
      </div>

      {/* Messages */}
      {errorMsg && (
        <div className="bg-rose-500/10 border-b border-rose-500/20 p-2.5 px-6 text-xs text-rose-400 flex items-center justify-between">
          <span>{errorMsg}</span>
          <button onClick={() => setErrorMsg(null)} className="text-slate-400 hover:text-slate-200">✕</button>
        </div>
      )}
      {successMsg && (
        <div className="bg-emerald-500/10 border-b border-emerald-500/20 p-2.5 px-6 text-xs text-emerald-400 flex items-center justify-between">
          <span>{successMsg}</span>
          <button onClick={() => setSuccessMsg(null)} className="text-slate-400 hover:text-slate-200">✕</button>
        </div>
      )}

      {/* Main Workspace Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Projects Left Drawer */}
        <div className="w-72 border-r border-slate-800 bg-slate-900/30 flex flex-col">
          <div className="p-3 border-b border-slate-800/80 flex items-center justify-between">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <FolderOpen className="w-3.5 h-3.5 text-sky-400" />
              <span>SOW Projects ({projects.length})</span>
            </span>
          </div>

          <div className="flex-1 overflow-y-auto divide-y divide-slate-800/50">
            {projects.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-500">
                No SOW projects found. Click <strong>+ New SOW Project</strong> to extract your first meeting transcript.
              </div>
            ) : (
              projects.map((proj) => {
                const isSelected = proj.project_id === selectedProjectId;
                return (
                  <button
                    key={proj.project_id}
                    onClick={() => { setSelectedProjectId(proj.project_id); setActiveTab("scope"); }}
                    className={`w-full text-left p-3.5 transition flex flex-col gap-1 ${
                      isSelected
                        ? "bg-slate-800/90 border-l-2 border-sky-400 text-slate-100"
                        : "hover:bg-slate-900/60 text-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold font-mono truncate max-w-[140px]">
                        {proj.project_id}
                      </span>
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                          proj.client_ready
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-800/60"
                            : "bg-amber-950 text-amber-400 border border-amber-800/60"
                        }`}
                      >
                        {proj.client_ready ? "APPROVED" : "DRAFT v" + proj.version}
                      </span>
                    </div>

                    <div className="text-[11px] text-slate-400 flex items-center gap-2 mt-0.5">
                      <span>{proj.requirements?.length || 0} requirements</span>
                      <span>•</span>
                      <span>v{proj.version}</span>
                    </div>

                    {proj.approved_by && (
                      <div className="text-[10px] text-emerald-400/90 truncate">
                        ✓ {proj.approved_by}
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Selected Project Main View */}
        <div className="flex-1 flex flex-col bg-slate-900/10 overflow-hidden">
          {selectedProject ? (
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Project Detail Header */}
              <div className="p-4 px-6 border-b border-slate-800 bg-slate-950/60 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-base font-bold font-mono text-slate-100">{selectedProject.project_id}</h2>
                    <span
                      className={`text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1 ${
                        selectedProject.client_ready
                          ? "bg-emerald-950/70 text-emerald-300 border border-emerald-800/60"
                          : "bg-amber-950/70 text-amber-300 border border-amber-800/60"
                      }`}
                    >
                      {selectedProject.client_ready ? (
                        <>
                          <ShieldCheck className="w-3.5 h-3.5" />
                          <span>Approved &amp; Client Ready</span>
                        </>
                      ) : (
                        <>
                          <Clock className="w-3.5 h-3.5" />
                          <span>Internal Draft (Pending Review)</span>
                        </>
                      )}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
                    <span>Version: <strong>{selectedProject.version}</strong></span>
                    <span>•</span>
                    <span>Updated: {new Date(selectedProject.updated_at).toLocaleString()}</span>
                    {selectedProject.approved_by && (
                      <>
                        <span>•</span>
                        <span className="text-emerald-400">
                          Approved by <strong>{selectedProject.approved_by}</strong> on{" "}
                          {new Date(selectedProject.approved_at || "").toLocaleDateString()}
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Tabs & Export Buttons */}
                <div className="flex items-center gap-2">
                  <div className="flex bg-slate-900 border border-slate-800 rounded-lg p-1">
                    <button
                      onClick={() => setActiveTab("scope")}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                        activeTab === "scope" ? "bg-slate-800 text-sky-400 font-semibold" : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Scope &amp; Feasibility
                    </button>
                    <button
                      onClick={() => setActiveTab("follow_up")}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                        activeTab === "follow_up" ? "bg-slate-800 text-sky-400 font-semibold" : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Follow-up Meeting Diff
                    </button>
                    <button
                      onClick={() => setActiveTab("proposal")}
                      className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                        activeTab === "proposal" ? "bg-slate-800 text-sky-400 font-semibold" : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      SOW Proposal
                    </button>
                  </div>

                  {/* Export Trigger */}
                  <a
                    href={api.getSOWExportUrl(selectedProject.project_id, "html", !selectedProject.client_ready)}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 transition"
                  >
                    <Printer className="w-3.5 h-3.5" />
                    <span>Export / Print</span>
                  </a>
                </div>
              </div>

              {/* Tab Contents */}
              <div className="flex-1 overflow-y-auto p-6">
                {/* 1. SCOPE & FEASIBILITY TAB */}
                {activeTab === "scope" && (
                  <div className="space-y-4 max-w-5xl mx-auto">
                    <div className="flex items-center justify-between pb-2">
                      <div>
                        <h3 className="text-sm font-bold text-slate-200">
                          Extracted Requirements &amp; Feasibility Verification ({selectedProject.requirements?.length || 0})
                        </h3>
                        <p className="text-xs text-slate-400">
                          Each item is independently cross-referenced with Knowledge Brain documentation to verify native capability.
                        </p>
                      </div>
                    </div>

                    <div className="space-y-3">
                      {selectedProject.requirements && selectedProject.requirements.length > 0 ? (
                        selectedProject.requirements.map((req: RequirementItem) => {
                          const cap = req.capability_status || "UNKNOWN";
                          const isNative = cap === "SUPPORTED";
                          const isCustom = cap === "NEEDS_CUSTOM_DEV" || cap === "PARTIAL_NATIVE";

                          return (
                            <div
                              key={req.id}
                              className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 space-y-3 shadow-sm hover:border-slate-700/80 transition"
                            >
                              <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-800/60 pb-2.5">
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-mono font-bold text-sky-400 bg-sky-950/60 border border-sky-800/40 px-2 py-0.5 rounded">
                                    {req.id}
                                  </span>
                                  <h4 className="text-xs font-bold text-slate-100">{req.title}</h4>
                                </div>

                                <div className="flex items-center gap-2">
                                  {/* Lifecycle Badge */}
                                  <span
                                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                                      req.lifecycle_status === "NEW"
                                        ? "bg-emerald-950 text-emerald-400 border border-emerald-800/60"
                                        : req.lifecycle_status === "CHANGED"
                                        ? "bg-amber-950 text-amber-400 border border-amber-800/60"
                                        : req.lifecycle_status === "REMOVED"
                                        ? "bg-rose-950 text-rose-400 border border-rose-800/60"
                                        : "bg-slate-800 text-slate-400 border border-slate-700"
                                    }`}
                                  >
                                    {req.lifecycle_status || "UNCHANGED"}
                                  </span>

                                  {/* Capability Status Badge */}
                                  <span
                                    className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full ${
                                      isNative
                                        ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60"
                                        : isCustom
                                        ? "bg-cyan-950 text-cyan-300 border border-cyan-800/60"
                                        : cap === "UNSUPPORTED"
                                        ? "bg-purple-950 text-purple-300 border border-purple-800/60"
                                        : "bg-slate-800 text-slate-300 border border-slate-700"
                                    }`}
                                  >
                                    {cap === "SUPPORTED"
                                      ? "NATIVE BD FEATURE"
                                      : cap === "NEEDS_CUSTOM_DEV"
                                      ? "CUSTOM DEVELOPMENT"
                                      : cap === "PARTIAL_NATIVE"
                                      ? "PARTIAL NATIVE + CUSTOM"
                                      : cap}
                                  </span>
                                </div>
                              </div>

                              <p className="text-xs text-slate-300 leading-relaxed">{req.description}</p>

                              {req.source_quote && (
                                <div className="bg-slate-950/60 border-l-2 border-slate-700 p-2.5 rounded-r-lg text-[11px] text-slate-400 italic">
                                  "{req.source_quote}"
                                </div>
                              )}

                              {/* Evidence Citations */}
                              {req.evidence_citations && req.evidence_citations.length > 0 && (
                                <div className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-2.5 text-[11px] space-y-1">
                                  <span className="font-semibold text-slate-400 block uppercase tracking-wider text-[10px]">
                                    Knowledge Brain Documentation Grounding:
                                  </span>
                                  {req.evidence_citations.map((cite, i) => (
                                    <div key={i} className="flex items-center justify-between text-slate-300">
                                      <span className="truncate pr-2">• {cite.title} {cite.section_heading ? `(${cite.section_heading})` : ""}</span>
                                      <a
                                        href={cite.url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="text-sky-400 hover:text-sky-300 flex items-center gap-1 shrink-0"
                                      >
                                        KB Doc <ExternalLink className="w-2.5 h-2.5" />
                                      </a>
                                    </div>
                                  ))}
                                </div>
                              )}

                              {/* Technical notes & hours */}
                              <div className="flex flex-wrap items-center justify-between text-[11px] text-slate-400 pt-1">
                                <div className="flex items-center gap-3">
                                  <span>Native Config: <strong className="text-emerald-400">{req.estimated_hours_native || 0} hrs</strong></span>
                                  <span>•</span>
                                  <span>Custom Dev: <strong className="text-cyan-400">{req.estimated_hours_custom || 0} hrs</strong></span>
                                </div>
                                {req.technical_notes && (
                                  <span className="text-slate-400 truncate max-w-md">{req.technical_notes}</span>
                                )}
                              </div>
                            </div>
                          );
                        })
                      ) : (
                        <div className="p-8 text-center text-xs text-slate-500">
                          No requirements recorded in this project scope.
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 2. FOLLOW-UP MEETING DIFF TAB */}
                {activeTab === "follow_up" && (
                  <div className="space-y-6 max-w-4xl mx-auto">
                    <div>
                      <h3 className="text-sm font-bold text-slate-200">Submit Follow-up Meeting Transcript</h3>
                      <p className="text-xs text-slate-400 mt-0.5">
                        The Multi-Agent Pipeline identifies scope changes (NEW, CHANGED, UNCHANGED, REMOVED) while preserving requirement identities.
                      </p>
                    </div>

                    <form onSubmit={handleProcessFollowUp} className="space-y-3 bg-slate-900 border border-slate-800 rounded-xl p-5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-slate-300">Follow-up Dialogue Transcript</label>
                        <button
                          type="button"
                          onClick={() => setFollowUpTranscript(sampleTranscripts[1].content)}
                          className="text-[11px] text-sky-400 hover:text-sky-300 font-medium"
                        >
                          Load Sample Follow-up
                        </button>
                      </div>

                      <textarea
                        rows={6}
                        required
                        placeholder="Paste dialogue from follow-up customer meeting..."
                        value={followUpTranscript}
                        onChange={(e) => setFollowUpTranscript(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 font-sans focus:outline-none focus:border-sky-500"
                      />

                      <div className="flex justify-end pt-2">
                        <button
                          type="submit"
                          disabled={isProcessingFollowUp || !followUpTranscript.trim()}
                          className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-lg text-xs font-semibold shadow-md shadow-sky-500/20 disabled:opacity-50"
                        >
                          <GitBranch className="w-3.5 h-3.5" />
                          <span>{isProcessingFollowUp ? "Analyzing Scope Diff..." : "Process Follow-up Meeting"}</span>
                        </button>
                      </div>
                    </form>

                    {/* Historical Changesets */}
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                        Scope Evolution History ({selectedProject.changesets?.length || 0})
                      </h4>
                      {selectedProject.changesets && selectedProject.changesets.length > 0 ? (
                        selectedProject.changesets.map((cs: ScopeChangeSet, idx: number) => (
                          <div key={idx} className="bg-slate-900/70 border border-slate-800 rounded-lg p-4 space-y-2 text-xs">
                            <div className="flex items-center justify-between text-slate-400 border-b border-slate-800/60 pb-1.5">
                              <span className="font-mono text-[11px] font-semibold text-slate-200">Changeset #{idx + 1}</span>
                              <span className="text-[10px]">{new Date(cs.detected_at).toLocaleString()}</span>
                            </div>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-1 text-[11px]">
                              <div className="p-2 rounded bg-slate-950 border border-slate-800/80">
                                <span className="text-emerald-400 font-bold block">{cs.added_requirements?.length || 0} Added</span>
                                <span className="text-slate-500 text-[10px]">NEW scope items</span>
                              </div>
                              <div className="p-2 rounded bg-slate-950 border border-slate-800/80">
                                <span className="text-amber-400 font-bold block">{cs.changed_requirements?.length || 0} Changed</span>
                                <span className="text-slate-500 text-[10px]">MODIFIED scope</span>
                              </div>
                              <div className="p-2 rounded bg-slate-950 border border-slate-800/80">
                                <span className="text-slate-300 font-bold block">{cs.unchanged_requirements?.length || 0} Unchanged</span>
                                <span className="text-slate-500 text-[10px]">CONFIRMED items</span>
                              </div>
                              <div className="p-2 rounded bg-slate-950 border border-slate-800/80">
                                <span className="text-rose-400 font-bold block">{cs.removed_requirements?.length || 0} Removed</span>
                                <span className="text-slate-500 text-[10px]">DELETED scope</span>
                              </div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="text-xs text-slate-500 p-4 border border-dashed border-slate-800 rounded-lg text-center">
                          Initial scope version (v1). No follow-up meetings processed yet.
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* 3. SOW PROPOSAL TAB */}
                {activeTab === "proposal" && (
                  <div className="space-y-6 max-w-4xl mx-auto">
                    {/* Approval Controls */}
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                        <div>
                          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                            {selectedProject.client_ready ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                            ) : (
                              <AlertTriangle className="w-4 h-4 text-amber-400" />
                            )}
                            <span>Human Approval Gate</span>
                          </h3>
                          <p className="text-xs text-slate-400 mt-0.5">
                            {selectedProject.client_ready
                              ? `Formally approved by ${selectedProject.approved_by}. Download client-ready document below.`
                              : "Review SOW draft below. Human approval is strictly required before client release."}
                          </p>
                        </div>

                        {!selectedProject.client_ready ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              placeholder="Reviewer Name"
                              value={approverName}
                              onChange={(e) => setApproverName(e.target.value)}
                              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
                            />
                            <button
                              onClick={handleApproveSOW}
                              disabled={isApproving || !approverName.trim()}
                              className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/20 disabled:opacity-50 transition"
                            >
                              {isApproving ? "Approving..." : "Approve SOW"}
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <a
                              href={api.getSOWExportUrl(selectedProject.project_id, "markdown", false)}
                              download
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                            >
                              <Download className="w-3.5 h-3.5" />
                              <span>Download .MD</span>
                            </a>
                            <a
                              href={api.getSOWExportUrl(selectedProject.project_id, "html", false)}
                              target="_blank"
                              rel="noreferrer"
                              className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/20 transition"
                            >
                              <Printer className="w-3.5 h-3.5" />
                              <span>Download PDF/HTML</span>
                            </a>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Proposal Markdown Rendered Card */}
                    <div className="bg-slate-950 border border-slate-800 rounded-xl p-8 space-y-4 shadow-xl relative">
                      {!selectedProject.client_ready && (
                        <div className="bg-amber-500/10 border border-amber-500/30 text-amber-300 p-3 rounded-lg text-xs flex items-center justify-between">
                          <span>
                            <strong>INTERNAL DRAFT:</strong> Not approved for client distribution.
                          </span>
                          <span className="font-mono text-[10px] uppercase font-bold tracking-wider">Unapproved</span>
                        </div>
                      )}

                      <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap font-sans text-slate-200 leading-relaxed">
                        {selectedProject.proposal_markdown || "Proposal draft not generated yet."}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center p-8 text-center text-slate-500 text-xs">
              Select an SOW project from the left drawer or create a new project from a meeting transcript.
            </div>
          )}
        </div>
      </div>

      {/* New Project Modal */}
      {showNewModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-xl w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-sky-400" />
                <span>Create New SOW Project from Meeting</span>
              </h3>
              <button onClick={() => setShowNewModal(false)} className="text-slate-400 hover:text-slate-200 text-xs px-2 py-1">
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateProject} className="space-y-3 text-xs">
              <div className="space-y-1">
                <span className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider block">
                  Quick Sample Meeting:
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setNewProjectId("proj_directory_migration");
                    setNewTranscript(sampleTranscripts[0].content);
                  }}
                  className="text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 px-2.5 py-1 rounded-lg transition"
                >
                  Load Sample Meeting (Staging &amp; Stripe Recurring)
                </button>
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1">Project Identifier (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. proj_client_migration"
                  value={newProjectId}
                  onChange={(e) => setNewProjectId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 font-mono focus:outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="text-slate-300 font-semibold block mb-1">Raw Meeting Transcript</label>
                <textarea
                  rows={8}
                  required
                  placeholder="Paste verbatim dialogue between client and consultant..."
                  value={newTranscript}
                  onChange={(e) => setNewTranscript(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-slate-200 font-sans focus:outline-none focus:border-sky-500 leading-relaxed"
                />
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-slate-800">
                <span className="text-[11px] text-slate-500">
                  Orchestrates Requirements Analyst, Capability Checker, Estimator &amp; Proposal Writer.
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setShowNewModal(false)}
                    className="px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={loading || !newTranscript.trim()}
                    className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-lg font-semibold shadow-md shadow-sky-500/20 disabled:opacity-50"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>{loading ? "Extracting..." : "Generate Scope & SOW"}</span>
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
