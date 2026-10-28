import React from "react";
import {
  LayoutDashboard,
  BookOpen,
  Globe,
  RefreshCw,
  MessageSquare,
  Inbox,
  CheckSquare,
  BarChart3,
  Settings,
  PenSquare,
  Activity,
  Cpu,
  Layers
} from "lucide-react";

export type ViewType =
  | "dashboard"
  | "inbox"
  | "reviews"
  | "meeting_sow"
  | "chat"
  | "knowledge"
  | "sitemaps"
  | "refresh_runs"
  | "quarantine"
  | "analytics"
  | "ai_models"
  | "settings";

interface SidebarProps {
  currentView: ViewType;
  onSelectView: (v: ViewType) => void;
  pendingReviewCount: number;
  quarantinedCount?: number;
  onOpenCompose: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentView,
  onSelectView,
  pendingReviewCount,
  quarantinedCount = 0,
  onOpenCompose
}) => {
  const navItems: Array<{
    id: ViewType;
    label: string;
    icon: React.ReactNode;
    badge?: number;
    badgeColor?: string;
  }> = [
    { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="w-4 h-4" /> },
    { id: "inbox", label: "Gmail Inbox", icon: <Inbox className="w-4 h-4" /> },
    {
      id: "reviews",
      label: "Human Reviews",
      icon: <CheckSquare className="w-4 h-4" />,
      badge: pendingReviewCount > 0 ? pendingReviewCount : undefined,
      badgeColor: "bg-sky-500 text-white"
    },
    { id: "meeting_sow", label: "Meeting-to-SOW", icon: <Layers className="w-4 h-4" /> },
    { id: "chat", label: "AI Knowledge Chat", icon: <MessageSquare className="w-4 h-4" /> },
    { id: "knowledge", label: "Knowledge Brain", icon: <BookOpen className="w-4 h-4" /> },
    { id: "sitemaps", label: "Sitemap Management", icon: <Globe className="w-4 h-4" /> },
    { id: "refresh_runs", label: "Refresh Runs", icon: <RefreshCw className="w-4 h-4" /> },
    {
      id: "quarantine",
      label: "Health & Archive",
      icon: <Activity className="w-4 h-4" />,
      badge: quarantinedCount > 0 ? quarantinedCount : undefined,
      badgeColor: "bg-amber-500 text-slate-950 font-bold"
    },
    { id: "analytics", label: "Automation Analytics", icon: <BarChart3 className="w-4 h-4" /> },
    { id: "ai_models", label: "AI Model Routing", icon: <Cpu className="w-4 h-4" /> },
    { id: "settings", label: "Settings", icon: <Settings className="w-4 h-4" /> }
  ];

  return (
    <aside className="w-64 border-r border-slate-800 bg-slate-900/50 flex flex-col justify-between p-3 select-none">
      <div className="space-y-4">
        {/* Compose Button (Gmail Style) */}
        <button
          onClick={onOpenCompose}
          className="w-full flex items-center justify-center gap-2.5 py-2.5 px-4 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-semibold shadow-lg shadow-sky-500/20 transition-all active:scale-[0.98]"
        >
          <PenSquare className="w-4 h-4" />
          <span>Compose Email</span>
        </button>

        {/* Navigation Section */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const isActive = currentView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectView(item.id)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? "bg-slate-800 text-sky-400 shadow-sm border border-slate-700/60 font-semibold"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <span className={isActive ? "text-sky-400" : "text-slate-500"}>{item.icon}</span>
                  <span>{item.label}</span>
                </div>
                {item.badge !== undefined && (
                  <span
                    className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${item.badgeColor || "bg-slate-800 text-slate-300"}`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* System Status Footprint */}
      <div className="p-3 bg-slate-950/60 border border-slate-800/80 rounded-xl space-y-1 text-[11px] text-slate-400">
        <div className="flex items-center justify-between text-slate-300 font-medium">
          <span>Local Engine Status</span>
          <span className="flex items-center gap-1 text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Active
          </span>
        </div>
        <div className="text-[10px] text-slate-500">
          FastAPI (8000) • Express (3000) • Task 3 (8002)
        </div>
      </div>
    </aside>
  );
};
