import React, { useState } from "react";
import { User } from "../types";
import { ShieldCheck, User as UserIcon, Lock, Mail, AlertCircle } from "lucide-react";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  onLogin: (email: string, pass: string) => Promise<User>;
  onRegister: (email: string, pass: string) => Promise<User>;
}

export const AuthModal: React.FC<AuthModalProps> = ({ isOpen, onClose, onLogin, onRegister }) => {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("demo.consultant@brilliantdirectories.com");
  const [password, setPassword] = useState("DemoPassword123!");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setIsLoading(true);
    setError(null);
    try {
      if (isRegister) {
        await onRegister(email, password);
      } else {
        await onLogin(email, password);
      }
      onClose();
    } catch (err: any) {
      setError(err?.message || "Authentication failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleUseDemoAccount = async () => {
    setEmail("demo.consultant@brilliantdirectories.com");
    setPassword("DemoPassword123!");
    setIsLoading(true);
    setError(null);
    try {
      await onLogin("demo.consultant@brilliantdirectories.com", "DemoPassword123!");
      onClose();
    } catch {
      // If demo user does not exist yet, register it!
      try {
        await onRegister("demo.consultant@brilliantdirectories.com", "DemoPassword123!");
        onClose();
      } catch (regErr: any) {
        setError(regErr?.message || "Demo account login failed");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8 max-w-md w-full space-y-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-slate-400 hover:text-slate-200 text-sm"
        >
          ✕
        </button>

        <div className="text-center space-y-1.5">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center mx-auto text-white shadow-lg shadow-sky-500/20">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-100">
            {isRegister ? "Create Demo Account" : "Local Demo Authentication"}
          </h2>
          <p className="text-xs text-slate-400">
            Secure PBKDF2-HMAC hashed sessions isolating crawl jobs, settings, and Gmail connections per user.
          </p>
        </div>

        {error && (
          <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-lg text-xs text-rose-300 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="text-slate-300 font-semibold block mb-1">Email Address</label>
            <div className="relative">
              <Mail className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-3" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2 pl-9 pr-3 text-slate-200 focus:outline-none focus:border-sky-500"
              />
            </div>
          </div>

          <div>
            <label className="text-slate-300 font-semibold block mb-1">Password</label>
            <div className="relative">
              <Lock className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-3" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2 pl-9 pr-3 text-slate-200 focus:outline-none focus:border-sky-500"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-2.5 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white rounded-lg font-semibold shadow-lg shadow-sky-500/20 transition disabled:opacity-50"
          >
            {isLoading ? "Authenticating..." : isRegister ? "Register Account" : "Sign In"}
          </button>
        </form>

        <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-xs">
          <button
            onClick={() => setIsRegister(!isRegister)}
            className="text-sky-400 hover:text-sky-300 font-medium"
          >
            {isRegister ? "Already have an account? Sign in" : "Need an account? Register"}
          </button>

          <button
            type="button"
            onClick={handleUseDemoAccount}
            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-medium border border-slate-700 text-[11px]"
          >
            One-Click Demo Login
          </button>
        </div>
      </div>
    </div>
  );
};
