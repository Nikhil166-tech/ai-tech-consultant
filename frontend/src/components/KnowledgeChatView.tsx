import React, { useState, useRef, useEffect } from "react";
import { ChatMessage } from "../types";
import { MessageSquare, Send, Sparkles, ExternalLink, ShieldAlert, Bot, User, CheckCircle2 } from "lucide-react";

interface KnowledgeChatViewProps {
  onSendMessage: (
    question: string,
    history: Array<{ role: string; content: string }>
  ) => Promise<{
    answer: string;
    citations: Array<{ title: string; section_heading: string; url: string }>;
    evidence_score: number;
    evidence_status: string;
    is_known: boolean;
    needs_human_review: boolean;
  }>;
}

export const KnowledgeChatView: React.FC<KnowledgeChatViewProps> = ({ onSendMessage }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "msg_welcome",
      role: "assistant",
      content:
        "Hello! I am your AI Tech Consultant knowledge assistant for Brilliant Directories. Ask me anything about product settings, payment gateways, search radius filters, DNS records, or membership plans.",
      timestamp: new Date().toISOString()
    }
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages.length, isLoading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userQuestion = input.trim();
    setInput("");

    const userMsg: ChatMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      content: userQuestion,
      timestamp: new Date().toISOString()
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      // Build conversation history format for Task 1 RAG endpoint
      const history = messages
        .filter((m) => m.id !== "msg_welcome")
        .map((m) => ({ role: m.role, content: m.content }));

      const res = await onSendMessage(userQuestion, history);

      const botMsg: ChatMessage = {
        id: `bot_${Date.now()}`,
        role: "assistant",
        content: res.answer,
        citations: res.citations,
        evidence_status: res.evidence_status,
        evidence_score: res.evidence_score,
        timestamp: new Date().toISOString()
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: `bot_err_${Date.now()}`,
          role: "assistant",
          content: `Unable to retrieve response: ${err?.message || "Knowledge Brain unavailable."}`,
          timestamp: new Date().toISOString()
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const sampleQuestions = [
    "How do I input my Stripe Publishable Key?",
    "How do members filter search results by 25 miles radius?",
    "What DNS records and nameservers should I set up?",
    "Where do I customize the website header and logo?"
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-4xl mx-auto p-6">
      {/* Header */}
      <div className="border-b border-slate-800 pb-4 mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-100">AI Knowledge Brain Chat</h1>
            <p className="text-[11px] text-slate-400">Hybrid semantic & lexical retrieval with verified documentation citations</p>
          </div>
        </div>
        <span className="text-[10px] bg-sky-950 text-sky-300 border border-sky-800 px-2 py-0.5 rounded font-mono">
          RAG v2.1 Grounded
        </span>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {msg.role === "assistant" && (
              <div className="w-7 h-7 rounded-lg bg-sky-600/20 border border-sky-500/40 flex items-center justify-center text-sky-400 shrink-0 mt-0.5">
                <Bot className="w-4 h-4" />
              </div>
            )}

            <div
              className={`max-w-2xl rounded-xl p-4 text-xs leading-relaxed space-y-2 ${
                msg.role === "user"
                  ? "bg-sky-600 text-white font-medium shadow-md shadow-sky-600/10"
                  : "bg-slate-900 border border-slate-800 text-slate-200 shadow-md shadow-black/20"
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>

              {/* Citations Footer */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="pt-2 border-t border-slate-800 mt-2 space-y-1">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                    Source Citations ({msg.citations.length}):
                  </span>
                  <div className="space-y-1">
                    {msg.citations.map((cite, i) => (
                      <div key={i} className="flex items-center justify-between text-[11px] text-slate-300">
                        <span className="truncate pr-2">• {cite.title} ({cite.section_heading})</span>
                        <a
                          href={cite.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-sky-400 hover:text-sky-300 flex items-center gap-1 text-[10px] shrink-0"
                        >
                          Official Doc <ExternalLink className="w-2.5 h-2.5" />
                        </a>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {msg.role === "user" && (
              <div className="w-7 h-7 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 shrink-0 mt-0.5">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3 justify-start">
            <div className="w-7 h-7 rounded-lg bg-sky-600/20 border border-sky-500/40 flex items-center justify-center text-sky-400 shrink-0">
              <Bot className="w-4 h-4 animate-spin" />
            </div>
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-400 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />
              <span>Querying verified knowledge base & synthesizing grounded response...</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Questions */}
      {messages.length <= 2 && (
        <div className="py-2 flex flex-wrap gap-1.5">
          {sampleQuestions.map((sq, i) => (
            <button
              key={i}
              onClick={() => setInput(sq)}
              className="text-[11px] bg-slate-900/80 hover:bg-slate-800 border border-slate-800 rounded-lg px-2.5 py-1 text-slate-300 transition"
            >
              {sq}
            </button>
          ))}
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <input
          type="text"
          placeholder="Ask a technical or product configuration question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 shadow-inner"
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="px-5 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-xl text-xs font-semibold shadow-lg shadow-sky-500/20 transition disabled:opacity-50 flex items-center gap-1.5"
        >
          <Send className="w-3.5 h-3.5" />
          <span>Send</span>
        </button>
      </form>
    </div>
  );
};
