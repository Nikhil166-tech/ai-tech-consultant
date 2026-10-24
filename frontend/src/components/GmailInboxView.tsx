import React, { useState } from "react";
import { InteractionRecord, CustomerEmail } from "../types";
import {
  Inbox,
  Send,
  FileText,
  Tag,
  Search,
  CheckCircle,
  Edit3,
  XCircle,
  ExternalLink,
  ShieldCheck,
  Clock,
  Sparkles,
  Paperclip,
  Check
} from "lucide-react";

interface GmailInboxViewProps {
  interactions: InteractionRecord[];
  onReview: (
    interactionId: string,
    action: "APPROVE" | "EDIT" | "REJECT",
    finalReply?: string,
    notes?: string,
    sendViaGmail?: boolean
  ) => Promise<void>;
  onSendViaGmail: (interactionId: string) => Promise<void>;
  isGmailConnected: boolean;
  filterLabel?: string;
}

export const GmailInboxView: React.FC<GmailInboxViewProps> = ({
  interactions,
  onReview,
  onSendViaGmail,
  isGmailConnected,
  filterLabel
}) => {
  const [selectedInteractionId, setSelectedInteractionId] = useState<string | null>(
    interactions[0]?.id || null
  );
  const [activeTab, setActiveTab] = useState<"inbox" | "sent" | "drafts">("inbox");
  const [selectedLabel, setSelectedLabel] = useState<string>(filterLabel || "ALL");
  const [search, setSearch] = useState("");
  const [editedBody, setEditedBody] = useState<string>("");
  const [isEditing, setIsEditing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectModal, setShowRejectModal] = useState(false);

  const selectedInteraction = interactions.find((i) => i.id === selectedInteractionId) || interactions[0];

  // Filtering
  const filteredInteractions = interactions.filter((item) => {
    // Tab filter
    if (activeTab === "inbox" && item.status !== "PENDING_REVIEW") {
      // Show pending in inbox, or all
    }
    if (activeTab === "sent" && item.status !== "APPROVED" && item.status !== "AUTO_SENT" && item.status !== "EDITED") {
      return false;
    }
    // Label filter
    if (selectedLabel !== "ALL") {
      if (
        item.classification?.parentSettingType !== selectedLabel &&
        item.classification?.specificLabel !== selectedLabel
      ) {
        return false;
      }
    }
    // Search query
    if (search.trim()) {
      const q = search.toLowerCase();
      const matchSubject = item.email.subject.toLowerCase().includes(q);
      const matchSender = item.email.senderEmail.toLowerCase().includes(q);
      const matchBody = item.email.body.toLowerCase().includes(q);
      if (!matchSubject && !matchSender && !matchBody) return false;
    }
    return true;
  });

  const handleSelect = (item: InteractionRecord) => {
    setSelectedInteractionId(item.id);
    setEditedBody(item.draft.body);
    setIsEditing(false);
  };

  const handleApprove = async (sendViaGmail: boolean = false) => {
    if (!selectedInteraction) return;
    setIsSubmitting(true);
    try {
      await onReview(selectedInteraction.id, "APPROVE", undefined, undefined, sendViaGmail);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSaveEditsAndSend = async (sendViaGmail: boolean = false) => {
    if (!selectedInteraction) return;
    setIsSubmitting(true);
    try {
      await onReview(selectedInteraction.id, "EDIT", editedBody, "Modified by human specialist in UI", sendViaGmail);
      setIsEditing(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!selectedInteraction) return;
    setIsSubmitting(true);
    try {
      await onReview(selectedInteraction.id, "REJECT", undefined, rejectReason || "Rejected by reviewer");
      setShowRejectModal(false);
      setRejectReason("");
    } finally {
      setIsSubmitting(false);
    }
  };

  const labels = [
    "ALL",
    "Design Settings",
    "Menu Manager",
    "Billing",
    "Filters",
    "Domain Management",
    "Staging",
    "General Settings"
  ];

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Sub-sidebar for Gmail navigation */}
      <div className="w-56 border-r border-slate-800 bg-slate-900/30 p-3 flex flex-col justify-between hidden md:flex">
        <div className="space-y-4">
          <div className="space-y-1">
            <button
              onClick={() => setActiveTab("inbox")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium ${
                activeTab === "inbox" ? "bg-slate-800 text-sky-400 font-semibold" : "text-slate-400 hover:bg-slate-800/40"
              }`}
            >
              <div className="flex items-center gap-2">
                <Inbox className="w-3.5 h-3.5" />
                <span>Inbox</span>
              </div>
              <span className="text-[10px] bg-sky-950 text-sky-400 px-1.5 py-0.5 rounded-full font-bold">
                {interactions.filter((i) => i.status === "PENDING_REVIEW").length}
              </span>
            </button>
            <button
              onClick={() => setActiveTab("sent")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium ${
                activeTab === "sent" ? "bg-slate-800 text-sky-400 font-semibold" : "text-slate-400 hover:bg-slate-800/40"
              }`}
            >
              <div className="flex items-center gap-2">
                <Send className="w-3.5 h-3.5" />
                <span>Sent</span>
              </div>
              <span className="text-[10px] text-slate-500">
                {interactions.filter((i) => i.status === "APPROVED" || i.status === "AUTO_SENT" || i.status === "EDITED").length}
              </span>
            </button>
            <button
              onClick={() => setActiveTab("drafts")}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium ${
                activeTab === "drafts" ? "bg-slate-800 text-sky-400 font-semibold" : "text-slate-400 hover:bg-slate-800/40"
              }`}
            >
              <div className="flex items-center gap-2">
                <FileText className="w-3.5 h-3.5" />
                <span>Drafts</span>
              </div>
            </button>
          </div>

          {/* Setting Labels */}
          <div className="pt-3 border-t border-slate-800/80">
            <div className="px-2 pb-2 text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Tag className="w-3 h-3 text-sky-400" />
              <span>Setting Types</span>
            </div>
            <div className="space-y-0.5">
              {labels.map((lbl) => (
                <button
                  key={lbl}
                  onClick={() => setSelectedLabel(lbl)}
                  className={`w-full text-left px-2.5 py-1.5 rounded-md text-[11px] truncate transition ${
                    selectedLabel === lbl
                      ? "bg-sky-500/10 text-sky-400 font-semibold border-l-2 border-sky-400"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
                  }`}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Message List */}
      <div className="w-80 lg:w-96 border-r border-slate-800 bg-slate-950 flex flex-col">
        {/* Search & Stats Bar */}
        <div className="p-3 border-b border-slate-800 flex items-center justify-between gap-2">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="Filter thread list..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/60"
            />
          </div>
        </div>

        {/* List items */}
        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
          {filteredInteractions.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-xs">
              No conversations found.
            </div>
          ) : (
            filteredInteractions.map((item) => {
              const isSelected = item.id === selectedInteraction?.id;
              const risk = item.classification?.kind?.riskLevel || "LOW";
              const isPending = item.status === "PENDING_REVIEW";

              return (
                <button
                  key={item.id}
                  onClick={() => handleSelect(item)}
                  className={`w-full text-left p-3.5 transition flex flex-col gap-1.5 ${
                    isSelected
                      ? "bg-slate-800/80 border-l-2 border-sky-400"
                      : "hover:bg-slate-900/60 text-slate-300"
                  }`}
                >
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-100 truncate max-w-[160px]">
                      {item.email.senderName || item.email.senderEmail}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      {new Date(item.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>

                  <div className="text-xs font-medium text-slate-200 truncate">
                    {item.email.subject}
                  </div>

                  <div className="text-[11px] text-slate-400 line-clamp-1">
                    {item.email.body}
                  </div>

                  <div className="flex items-center gap-1.5 pt-1">
                    {/* Status Badge */}
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                        item.status === "AUTO_SENT"
                          ? "bg-purple-950/60 text-purple-300 border border-purple-800/40"
                          : item.status === "APPROVED"
                          ? "bg-emerald-950/60 text-emerald-300 border border-emerald-800/40"
                          : item.status === "EDITED"
                          ? "bg-blue-950/60 text-blue-300 border border-blue-800/40"
                          : item.status === "REJECTED"
                          ? "bg-rose-950/60 text-rose-300 border border-rose-800/40"
                          : "bg-sky-950/60 text-sky-300 border border-sky-800/40"
                      }`}
                    >
                      {item.status}
                    </span>

                    {/* Setting Type Label */}
                    <span className="text-[9px] bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded truncate max-w-[100px]">
                      {item.classification?.specificLabel || item.classification?.parentSettingType || "General"}
                    </span>

                    {/* Risk Badge */}
                    {risk !== "LOW" && (
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
                          risk === "CRITICAL"
                            ? "bg-red-950 text-red-300 border border-red-800"
                            : "bg-amber-950 text-amber-300 border border-amber-800"
                        }`}
                      >
                        {risk}
                      </span>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Main Conversation / AI Draft Detail View */}
      <div className="flex-1 flex flex-col bg-slate-900/40 overflow-y-auto">
        {selectedInteraction ? (
          <div className="p-6 space-y-6 max-w-4xl mx-auto w-full">
            {/* Header info */}
            <div className="border-b border-slate-800 pb-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-bold text-slate-100">{selectedInteraction.email.subject}</h1>
                <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
                  <span>From: <strong className="text-slate-200">{selectedInteraction.email.senderEmail}</strong></span>
                  <span>•</span>
                  <span>{new Date(selectedInteraction.createdAt).toLocaleString()}</span>
                  {selectedInteraction.gmailMessageId && (
                    <>
                      <span>•</span>
                      <span className="text-emerald-400 font-mono text-[10px]">Gmail ID: {selectedInteraction.gmailMessageId.slice(0, 10)}...</span>
                    </>
                  )}
                </div>
              </div>

              {/* Taxonomy / Auto-send status card */}
              <div className="flex items-center gap-2 text-xs bg-slate-950/70 border border-slate-800 px-3 py-1.5 rounded-lg">
                <Tag className="w-3.5 h-3.5 text-sky-400" />
                <span className="text-slate-300 font-medium">
                  {selectedInteraction.classification?.parentSettingType} →{" "}
                  <span className="text-sky-300">{selectedInteraction.classification?.specificLabel}</span>
                </span>
              </div>
            </div>

            {/* Original Customer Message Card */}
            <div className="bg-slate-950/80 border border-slate-800/80 rounded-xl p-4 space-y-2 shadow-sm">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="font-semibold text-slate-300">Customer Inquiry</span>
                <span className="text-[11px] font-mono">{selectedInteraction.email.id}</span>
              </div>
              <div className="text-xs text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                {selectedInteraction.email.body}
              </div>
            </div>

            {/* AI-Grounded Draft Section */}
            <div className="bg-slate-900 border border-slate-700/80 rounded-xl p-5 space-y-4 shadow-lg shadow-black/20">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-sky-400" />
                  <h2 className="text-sm font-bold text-slate-100">AI-Synthesized Customer Reply</h2>
                  <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono">
                    {selectedInteraction.draft.promptVersion}
                  </span>
                </div>

                <div className="flex items-center gap-2">
                  {selectedInteraction.draft.autoSendEligible ? (
                    <span className="flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-950/50 border border-emerald-800/60 px-2.5 py-0.5 rounded-full font-medium">
                      <ShieldCheck className="w-3.5 h-3.5" />
                      Auto-Send Eligible
                    </span>
                  ) : (
                    <span className="text-[11px] text-amber-400 bg-amber-950/50 border border-amber-800/60 px-2.5 py-0.5 rounded-full font-medium" title={selectedInteraction.draft.blockReason}>
                      Requires Human Review
                    </span>
                  )}
                </div>
              </div>

              {/* Verified Citations List */}
              {selectedInteraction.draft.citations && selectedInteraction.draft.citations.length > 0 && (
                <div className="bg-slate-950/60 border border-slate-800 rounded-lg p-3 space-y-1.5">
                  <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center gap-1">
                    <Paperclip className="w-3 h-3 text-sky-400" />
                    <span>Verified Knowledge Documentation Evidence</span>
                  </div>
                  <div className="space-y-1">
                    {selectedInteraction.draft.citations.map((cite, idx) => (
                      <div key={idx} className="flex items-center justify-between text-xs text-slate-300">
                        <span className="truncate pr-2">• {cite.title} ({cite.section_heading})</span>
                        <a
                          href={cite.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-sky-400 hover:text-sky-300 flex items-center gap-1 text-[11px]"
                        >
                          Source <ExternalLink className="w-2.5 h-2.5" />
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Draft Body / Editor */}
              {isEditing ? (
                <div className="space-y-2">
                  <textarea
                    rows={8}
                    value={editedBody}
                    onChange={(e) => setEditedBody(e.target.value)}
                    className="w-full bg-slate-950 border border-sky-500/80 rounded-lg p-3 text-xs text-slate-100 font-mono leading-relaxed focus:outline-none focus:ring-1 focus:ring-sky-500"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setIsEditing(false)}
                      className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:bg-slate-800"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => handleSaveEditsAndSend(false)}
                      disabled={isSubmitting}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 hover:bg-sky-500 text-white"
                    >
                      Save Changes
                    </button>
                    {isGmailConnected && (
                      <button
                        onClick={() => handleSaveEditsAndSend(true)}
                        disabled={isSubmitting}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1"
                      >
                        <Send className="w-3 h-3" />
                        Save & Send via Gmail
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3.5 text-xs text-slate-200 whitespace-pre-wrap font-sans leading-relaxed">
                  {selectedInteraction.status === "APPROVED" || selectedInteraction.status === "EDITED" || selectedInteraction.status === "AUTO_SENT"
                    ? selectedInteraction.finalSentReply || selectedInteraction.draft.body
                    : selectedInteraction.draft.body}
                </div>
              )}

              {/* Actions Footer */}
              {selectedInteraction.status === "PENDING_REVIEW" && !isEditing && (
                <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleApprove(false)}
                      disabled={isSubmitting}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/20 transition"
                    >
                      <CheckCircle className="w-3.5 h-3.5" />
                      Approve (Unchanged)
                    </button>

                    {isGmailConnected && (
                      <button
                        onClick={() => handleApprove(true)}
                        disabled={isSubmitting}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-sky-600 hover:bg-sky-500 text-white shadow-md shadow-sky-600/20 transition"
                      >
                        <Send className="w-3.5 h-3.5" />
                        Approve & Send via Gmail
                      </button>
                    )}

                    <button
                      onClick={() => {
                        setEditedBody(selectedInteraction.draft.body);
                        setIsEditing(true);
                      }}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                      Edit Response
                    </button>
                  </div>

                  <button
                    onClick={() => setShowRejectModal(true)}
                    className="flex items-center gap-1 px-3 py-2 rounded-lg text-xs font-medium text-rose-400 hover:bg-rose-950/40 border border-rose-900/50 transition"
                  >
                    <XCircle className="w-3.5 h-3.5" />
                    Reject Draft
                  </button>
                </div>
              )}

              {/* Already resolved notification */}
              {selectedInteraction.status !== "PENDING_REVIEW" && (
                <div className="flex items-center justify-between text-xs text-slate-400 pt-2 border-t border-slate-800">
                  <span className="flex items-center gap-1 text-emerald-400 font-medium">
                    <Check className="w-4 h-4" />
                    Resolved: {selectedInteraction.status} by {selectedInteraction.reviewerId || "Automated Agent"}
                  </span>
                  {selectedInteraction.finalSentReply && !selectedInteraction.gmailMessageId && isGmailConnected && (
                    <button
                      onClick={() => onSendViaGmail(selectedInteraction.id)}
                      className="flex items-center gap-1 px-3 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded text-xs font-semibold"
                    >
                      <Send className="w-3 h-3" />
                      Deliver via Gmail Now
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
            Select a message to view the conversation and AI draft.
          </div>
        )}
      </div>

      {/* Reject Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 max-w-md w-full space-y-4">
            <h3 className="text-sm font-bold text-slate-100">Reject AI Draft</h3>
            <p className="text-xs text-slate-400">
              Rejecting this draft resets the autonomy streak for this setting type and requires a specialist to handle manually.
            </p>
            <textarea
              rows={3}
              placeholder="Reason for rejection (e.g., incorrect instructions, out-of-scope question)..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 focus:outline-none focus:border-rose-500"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowRejectModal(false)}
                className="px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={isSubmitting}
                className="px-3 py-1.5 text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white rounded-lg"
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
