"use client";
import Wordmark from "./Wordmark";

/** Minimal mobile layout for participant pages (no staff navigation). */
export default function PhoneShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="px-5 py-4 border-b border-line bg-panel"><Wordmark /></header>
      <main className="px-5 py-6 max-w-xl mx-auto space-y-5">{children}</main>
    </div>
  );
}

export const TOKEN_KEY = "bdas_run_token";

export function savedToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function saveToken(t: string) {
  try { localStorage.setItem(TOKEN_KEY, t); } catch {}
}
