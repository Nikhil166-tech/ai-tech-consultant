import React from "react";
import { User, GmailAccountStatus } from "../types";
import { ShieldAlert, Mail, RefreshCw, LogOut, User as UserIcon, CheckCircle2, AlertTriangle } from "lucide-react";

interface NavbarProps {
  user: User | null;
  gmailStatus: GmailAccountStatus;
  emergencyStop: boolean;
  onToggleEmergencyStop: () => void;
  onSyncGmail: () => void;
  onOpenAuth: () => void;
  onLogout: () => void;
  isSyncing: boolean;
  searchQuery: string;
  onSearchChange: (q: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  user,
  gmailStatus,
  emergencyStop,
  onToggleEmergencyStop,
  onSyncGmail,
  onOpenAuth,
  onLogout,
  isSyncing,
  searchQuery,
  onSearchChange
}) => {
  return (
    <header className="h-16 border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-30 px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center font-bold text-white shadow-lg shadow-sky-500/20">
          AI
        </div>
        <div>
          <span className="font-semibold text-slate-100 text-sm tracking-tight block">AI Tech Consultant</span>
          <span className="text-[11px] text-sky-400 font-mono tracking-wide uppercase">Knowledge Brain & Inbox</span>
        </div>
      </div>

      {/* Global Search Bar */}
      <div className="max-w-md w-full mx-6 hidden md:block">
        <div className="relative">
          <input
            type="text"
            placeholder="Search knowledge, emails, citations, or URLs..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full bg-slate-950/70 border border-slate-800 rounded-full py-1.5 pl-4 pr-10 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/60 focus:ring-1 focus:ring-sky-500/30 transition-all"
          />
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Gmail Connection Status Pill */}
        <div
          className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${
            gmailStatus.isConnected
              ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
              : "bg-slate-800/40 border-slate-700 text-slate-400"
          }`}
          title={gmailStatus.isConnected ? `Connected: ${gmailStatus.email}` : "Gmail Disconnected"}
        >
          <Mail className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">
            {gmailStatus.isConnected ? (gmailStatus.isMock ? "Mock Gmail" : "Gmail Connected") : "Gmail Offline"}
          </span>
          {gmailStatus.isConnected && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />}
        </div>

        {/* Sync Gmail Button */}
        {gmailStatus.isConnected && (
          <button
            onClick={onSyncGmail}
            disabled={isSyncing}
            className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-medium border border-slate-700 transition"
            title="Fetch new incoming emails from Gmail"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin text-sky-400" : ""}`} />
            <span className="hidden sm:inline">Sync</span>
          </button>
        )}

        {/* Emergency Stop Switch */}
        <button
          onClick={onToggleEmergencyStop}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold border transition shadow-sm ${
            emergencyStop
              ? "bg-rose-950 border-rose-600 text-rose-200 hover:bg-rose-900"
              : "bg-slate-800/80 hover:bg-slate-800 border-slate-700 text-slate-300"
          }`}
          title={emergencyStop ? "Emergency Stop is ACTIVE (auto-send disabled)" : "Emergency Stop is STANDBY"}
        >
          <ShieldAlert className={`w-3.5 h-3.5 ${emergencyStop ? "text-rose-400 animate-bounce" : "text-slate-400"}`} />
          <span>{emergencyStop ? "EMERGENCY STOP" : "Emergency Stop"}</span>
        </button>

        {/* User Account / Profile */}
        {user ? (
          <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
            <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-sky-300">
              {user.email.charAt(0).toUpperCase()}
            </div>
            <div className="hidden lg:block text-left text-xs">
              <span className="block font-medium text-slate-200 truncate max-w-[120px]">{user.email}</span>
              <span className="text-[10px] text-slate-400 uppercase tracking-wider">{user.role}</span>
            </div>
            <button
              onClick={onLogout}
              className="text-slate-400 hover:text-rose-400 p-1.5 rounded-md hover:bg-slate-800 transition"
              title="Logout"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={onOpenAuth}
            className="flex items-center gap-1.5 px-3 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-md shadow-sky-600/20 transition"
          >
            <UserIcon className="w-3.5 h-3.5" />
            <span>Login / Demo</span>
          </button>
        )}
      </div>
    </header>
  );
};
