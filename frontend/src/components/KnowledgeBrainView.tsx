import React, { useState } from "react";
import { BookOpen, Search, ExternalLink, FileText, CheckCircle2 } from "lucide-react";

interface KnowledgeBrainViewProps {
  articles: any[];
}

export const KnowledgeBrainView: React.FC<KnowledgeBrainViewProps> = ({ articles }) => {
  const [search, setSearch] = useState("");

  const normalizedArticles = React.useMemo(() => {
    return (articles || []).map((a, idx) => {
      if (typeof a === "string") {
        const parts = a.split("/").filter(Boolean);
        const name = parts[parts.length - 1] || a;
        const cleanTitle = decodeURIComponent(name).replace(/[-_]/g, " ").replace(/\.\w+$/, "");
        return {
          id: a,
          url: a,
          title: cleanTitle ? cleanTitle.charAt(0).toUpperCase() + cleanTitle.slice(1) : a,
          category: "Documentation",
          chunks_count: 1,
          content: `Documentation URL indexed into Knowledge Brain:\n${a}`
        };
      }
      return {
        id: a.id || a.url || `art_${idx}`,
        url: a.url || a.id || "",
        title: a.title || a.url || "Knowledge Article",
        category: a.category || "General",
        chunks_count: a.chunks_count || 1,
        content: a.content || a.body_text || a.summary || "No raw text preview available."
      };
    });
  }, [articles]);

  const [selectedArticle, setSelectedArticle] = useState<any | null>(null);

  React.useEffect(() => {
    if (!selectedArticle && normalizedArticles.length > 0) {
      setSelectedArticle(normalizedArticles[0]);
    }
  }, [normalizedArticles.length]);

  const filtered = normalizedArticles.filter((a) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (a.title || "").toLowerCase().includes(q) || (a.url || "").toLowerCase().includes(q);
  });

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Articles Sidebar */}
      <div className="w-80 lg:w-96 border-r border-slate-800 bg-slate-950 flex flex-col">
        <div className="p-4 border-b border-slate-800 space-y-2">
          <div className="flex items-center justify-between">
            <h1 className="text-xs font-bold text-slate-100 flex items-center gap-1.5 uppercase tracking-wider">
              <BookOpen className="w-4 h-4 text-sky-400" />
              <span>Knowledge Brain ({articles.length})</span>
            </h1>
          </div>
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="Search indexed articles..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg py-1.5 pl-8 pr-3 text-xs text-slate-200 focus:outline-none focus:border-sky-500"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
          {filtered.length === 0 ? (
            <div className="p-8 text-center text-slate-500 text-xs">No articles found.</div>
          ) : (
            filtered.map((art) => {
              const isSelected = art.id === selectedArticle?.id;
              return (
                <button
                  key={art.id}
                  onClick={() => setSelectedArticle(art)}
                  className={`w-full text-left p-3.5 transition flex flex-col gap-1 ${
                    isSelected ? "bg-slate-800/80 border-l-2 border-sky-400" : "hover:bg-slate-900/60"
                  }`}
                >
                  <span className="font-semibold text-xs text-slate-200 line-clamp-1">{art.title}</span>
                  <span className="text-[11px] text-slate-500 font-mono truncate">{art.url}</span>
                  <div className="flex items-center gap-2 pt-1 text-[10px]">
                    <span className="text-emerald-400 font-bold bg-emerald-950/60 px-1.5 py-0.5 rounded">
                      ACTIVE
                    </span>
                    <span className="text-slate-400">{art.chunks_count || 1} chunks</span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Article Detail Viewer */}
      <div className="flex-1 bg-slate-900/40 p-8 overflow-y-auto">
        {selectedArticle ? (
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="border-b border-slate-800 pb-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] bg-slate-800 text-sky-400 font-mono px-2 py-0.5 rounded">
                  {selectedArticle.id}
                </span>
                <a
                  href={selectedArticle.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-xs text-sky-400 hover:text-sky-300"
                >
                  <span>Open Source</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              <h2 className="text-xl font-bold text-slate-100">{selectedArticle.title}</h2>
              <p className="text-xs text-slate-400 font-mono">{selectedArticle.url}</p>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-xl p-5 space-y-3 shadow-lg">
              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                Article Body Content
              </span>
              <div className="text-xs text-slate-300 leading-relaxed font-sans whitespace-pre-wrap">
                {selectedArticle.content || selectedArticle.summary || "No raw text preview available."}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-500 text-xs">
            Select an article from the left to inspect its indexed chunks and evidence metadata.
          </div>
        )}
      </div>
    </div>
  );
};
