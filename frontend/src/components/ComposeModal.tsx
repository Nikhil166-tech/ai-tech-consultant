import React, { useState } from "react";
import { PenSquare, Send, Save, Mail, Sparkles, CheckCircle2, AlertCircle } from "lucide-react";
import { CustomerEmail } from "../types";
import { api } from "../api";

interface ComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSimulateIncoming: (email: CustomerEmail) => Promise<void>;
  onSendViaGmail?: (to: string, subject: string, body: string) => Promise<void>;
  onRefreshInbox?: () => void;
  isGmailConnected: boolean;
}

export const ComposeModal: React.FC<ComposeModalProps> = ({
  isOpen,
  onClose,
  onSimulateIncoming,
  onRefreshInbox,
  isGmailConnected
}) => {
  const [mode, setMode] = useState<"outgoing" | "simulate">("outgoing");

  // Outgoing email state
  const [toRecipient, setToRecipient] = useState("");
  const [outSubject, setOutSubject] = useState("");
  const [outBody, setOutBody] = useState("");
  const [sendViaGmail, setSendViaGmail] = useState(isGmailConnected);

  // Simulate customer incoming email state
  const [senderEmail, setSenderEmail] = useState("webmaster@directory.com");
  const [senderName, setSenderName] = useState("Director Smith");
  const [simSubject, setSimSubject] = useState("How do I configure our Stripe Publishable Key?");
  const [simBody, setSimBody] = useState(
    "Hi support, where in the admin panel do we input our Stripe Publishable Key and Webhook signing secret?"
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  if (!isOpen) return null;

  const handleOutgoingSubmit = async (saveDraft: boolean) => {
    if (!toRecipient.trim() || !outSubject.trim() || !outBody.trim()) {
      setStatusMsg({ type: "error", text: "Please fill in recipient, subject, and message body." });
      return;
    }

    setIsSubmitting(true);
    setStatusMsg(null);
    try {
      await api.composeMessage({
        to: toRecipient.trim(),
        subject: outSubject.trim(),
        body: outBody.trim(),
        saveDraft,
        sendViaGmail: !saveDraft && sendViaGmail && isGmailConnected
      });
      if (onRefreshInbox) onRefreshInbox();
      onClose();
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message || "Failed to save message." });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSimulateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!simSubject.trim() || !simBody.trim()) return;

    setIsSubmitting(true);
    setStatusMsg(null);
    try {
      const email: CustomerEmail = {
        id: `email_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        senderEmail: senderEmail.trim(),
        senderName: senderName.trim() || undefined,
        subject: simSubject.trim(),
        body: simBody.trim(),
        receivedAt: new Date().toISOString()
      };
      await onSimulateIncoming(email);
      if (onRefreshInbox) onRefreshInbox();
      onClose();
    } catch (err: any) {
      setStatusMsg({ type: "error", text: err.message || "Simulation failed." });
    } finally {
      setIsSubmitting(false);
    }
  };

  const sampleTemplates = [
    {
      title: "Stripe Key Setup",
      subj: "Stripe Publishable Key configuration",
      bdy: "Where do we input our Stripe keys and how do transaction fees work?"
    },
    {
      title: "Header / Logo",
      subj: "Updating site header branding",
      bdy: "How do I upload a new logo to the header and change top navigation menu colors?"
    },
    {
      title: "Search Radius",
      subj: "Search distance radius filter",
      bdy: "Can members search listings within a 50-mile radius or filter by zip code?"
    },
    {
      title: "High Risk Refund",
      subj: "Billing dispute - refund $149 immediately",
      bdy: "I was billed twice without permission. Refund me now or I will contact my bank to chargeback."
    }
  ];

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-xl w-full space-y-4 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => { setMode("outgoing"); setStatusMsg(null); }}
              className={`text-xs font-bold px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition ${
                mode === "outgoing"
                  ? "bg-sky-500/20 text-sky-400 border border-sky-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <PenSquare className="w-3.5 h-3.5" />
              <span>New Message</span>
            </button>
            <button
              type="button"
              onClick={() => { setMode("simulate"); setStatusMsg(null); }}
              className={`text-xs font-bold px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition ${
                mode === "simulate"
                  ? "bg-indigo-500/20 text-indigo-400 border border-indigo-500/40"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Simulate Customer Test</span>
            </button>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xs px-2 py-1">
            ✕
          </button>
        </div>

        {statusMsg && (
          <div
            className={`p-2.5 rounded-lg text-xs flex items-center gap-2 ${
              statusMsg.type === "error"
                ? "bg-rose-500/10 border border-rose-500/30 text-rose-400"
                : "bg-emerald-500/10 border border-emerald-500/30 text-emerald-400"
            }`}
          >
            {statusMsg.type === "error" ? <AlertCircle className="w-4 h-4 shrink-0" /> : <CheckCircle2 className="w-4 h-4 shrink-0" />}
            <span>{statusMsg.text}</span>
          </div>
        )}

        {mode === "outgoing" ? (
          <div className="space-y-3 text-xs">
            <div>
              <label className="text-slate-300 font-semibold block mb-1">To (Recipient Email)</label>
              <input
                type="email"
                placeholder="client@company.com"
                value={toRecipient}
                onChange={(e) => setToRecipient(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
              />
            </div>

            <div>
              <label className="text-slate-300 font-semibold block mb-1">Subject</label>
              <input
                type="text"
                placeholder="Subject line"
                value={outSubject}
                onChange={(e) => setOutSubject(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500"
              />
            </div>

            <div>
              <label className="text-slate-300 font-semibold block mb-1">Message Body</label>
              <textarea
                rows={6}
                placeholder="Write your email reply or message..."
                value={outBody}
                onChange={(e) => setOutBody(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-slate-200 focus:outline-none focus:border-sky-500 leading-relaxed font-sans"
              />
            </div>

            {isGmailConnected && (
              <label className="flex items-center gap-2 cursor-pointer text-[11px] text-slate-400 pt-1">
                <input
                  type="checkbox"
                  checked={sendViaGmail}
                  onChange={(e) => setSendViaGmail(e.target.checked)}
                  className="rounded border-slate-700 bg-slate-950 text-sky-500 focus:ring-0"
                />
                <span>Send through connected Gmail account</span>
              </label>
            )}

            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <span className="text-[11px] text-slate-500">
                {isGmailConnected ? "Gmail connected & ready." : "Offline/Local mode. Outgoing messages stored in Sent/Drafts."}
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => handleOutgoingSubmit(true)}
                  disabled={isSubmitting}
                  className="flex items-center gap-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg font-medium border border-slate-700 disabled:opacity-50"
                >
                  <Save className="w-3.5 h-3.5 text-slate-400" />
                  <span>Save Draft</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleOutgoingSubmit(false)}
                  disabled={isSubmitting}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-lg font-semibold shadow-md shadow-sky-500/20 disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{isSubmitting ? "Sending..." : "Send Message"}</span>
                </button>
              </div>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSimulateSubmit} className="space-y-3 text-xs">
            <div className="space-y-1">
              <span className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider block">
                Quick Test Scenarios:
              </span>
              <div className="flex flex-wrap gap-1.5">
                {sampleTemplates.map((tpl, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      setSimSubject(tpl.subj);
                      setSimBody(tpl.bdy);
                    }}
                    className="text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 px-2.5 py-1 rounded-lg transition"
                  >
                    {tpl.title}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-slate-300 font-semibold block mb-1">Customer Email</label>
                <input
                  type="email"
                  required
                  value={senderEmail}
                  onChange={(e) => setSenderEmail(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                />
              </div>
              <div>
                <label className="text-slate-300 font-semibold block mb-1">Customer Name</label>
                <input
                  type="text"
                  value={senderName}
                  onChange={(e) => setSenderName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500"
                />
              </div>
            </div>

            <div>
              <label className="text-slate-300 font-semibold block mb-1">Subject</label>
              <input
                type="text"
                required
                value={simSubject}
                onChange={(e) => setSimSubject(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500"
              />
            </div>

            <div>
              <label className="text-slate-300 font-semibold block mb-1">Message Body</label>
              <textarea
                rows={5}
                required
                value={simBody}
                onChange={(e) => setSimBody(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-slate-200 focus:outline-none focus:border-sky-500 leading-relaxed font-sans"
              />
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <span className="text-[11px] text-slate-500">
                Runs AI classification, RAG retrieval &amp; draft generation.
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:bg-slate-800 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-lg font-semibold shadow-md shadow-sky-500/20 disabled:opacity-50"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>{isSubmitting ? "Processing..." : "Process into Inbox"}</span>
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
