import React, { useState } from "react";
import { PenSquare, Send, Mail, Sparkles } from "lucide-react";
import { CustomerEmail } from "../types";

interface ComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSimulateIncoming: (email: CustomerEmail) => Promise<void>;
  onSendViaGmail?: (to: string, subject: string, body: string) => Promise<void>;
  isGmailConnected: boolean;
}

export const ComposeModal: React.FC<ComposeModalProps> = ({
  isOpen,
  onClose,
  onSimulateIncoming,
  isGmailConnected
}) => {
  const [senderEmail, setSenderEmail] = useState("webmaster@directory.com");
  const [senderName, setSenderName] = useState("Director Smith");
  const [subject, setSubject] = useState("How do I configure our Stripe Publishable Key?");
  const [body, setBody] = useState(
    "Hi support, where in the admin panel do we input our Stripe Publishable Key and Webhook signing secret?"
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subject.trim() || !body.trim()) return;

    setIsSubmitting(true);
    try {
      const email: CustomerEmail = {
        id: `email_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
        senderEmail: senderEmail.trim(),
        senderName: senderName.trim() || undefined,
        subject: subject.trim(),
        body: body.trim(),
        receivedAt: new Date().toISOString()
      };
      await onSimulateIncoming(email);
      onClose();
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
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-xl w-full space-y-5 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
            <PenSquare className="w-4 h-4 text-sky-400" />
            <span>Simulate Incoming Customer Email</span>
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xs">
            ✕
          </button>
        </div>

        {/* Quick Template Fillers */}
        <div className="space-y-1">
          <span className="text-[11px] text-slate-400 font-semibold uppercase tracking-wider block">
            Quick Scenarios:
          </span>
          <div className="flex flex-wrap gap-1.5">
            {sampleTemplates.map((tpl, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  setSubject(tpl.subj);
                  setBody(tpl.bdy);
                }}
                className="text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 px-2.5 py-1 rounded-lg transition"
              >
                {tpl.title}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3 text-xs">
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
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 focus:outline-none focus:border-sky-500"
            />
          </div>

          <div>
            <label className="text-slate-300 font-semibold block mb-1">Message Body</label>
            <textarea
              rows={5}
              required
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-slate-200 focus:outline-none focus:border-sky-500 leading-relaxed font-sans"
            />
          </div>

          <div className="flex items-center justify-between pt-3 border-t border-slate-800">
            <span className="text-[11px] text-slate-500">
              Processes through classification, RAG evidence retrieval, and autonomy streak evaluation.
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
      </div>
    </div>
  );
};
