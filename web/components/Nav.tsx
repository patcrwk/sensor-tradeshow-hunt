"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "./BrandProvider";
import Wordmark from "./Wordmark";

const ITEMS = [
  { href: "/display", label: "Display", staff: false },
  { href: "/hunt", label: "Hunt", staff: true },
  { href: "/course", label: "Course Setup", staff: true },
  { href: "/explorer", label: "Recording Explorer", staff: false },
  { href: "/admin", label: "Admin", staff: true },
];

export default function Nav() {
  const path = usePathname();
  const { auth, isStaff, reloadAuth } = useAuth();
  const items = ITEMS.filter((i) => !i.staff || isStaff);
  return (
    <header className="border-b border-line bg-panel sticky top-0 z-30">
      <div className="mx-auto max-w-[1600px] px-4 flex items-center gap-6 h-14">
        <Link href="/" className="flex items-center"><Wordmark /></Link>
        <nav className="flex gap-1 overflow-x-auto">
          {items.map((i) => {
            const on = path === i.href || path.startsWith(i.href + "/");
            return (
              <Link key={i.href} href={i.href}
                className={`px-3 py-2 rounded-md font-semibold whitespace-nowrap ${on ? "bg-brand text-black" : "text-muted hover:text-text"}`}>
                {i.label}
              </Link>
            );
          })}
        </nav>
        {auth?.required && (
          <div className="ml-auto">
            {isStaff
              ? <button className="text-sm text-muted hover:text-text" onClick={async () => { await api("/api/auth/logout", { method: "POST" }); reloadAuth(); }}>Staff log out</button>
              : <Link href={`/login?next=${encodeURIComponent(path)}`} className="text-sm text-muted hover:text-text">Staff login</Link>}
          </div>
        )}
      </div>
    </header>
  );
}

export function Page({ title, actions, children, wide, staff }: { title?: string; actions?: React.ReactNode; children: React.ReactNode; wide?: boolean; staff?: boolean }) {
  const { auth, isStaff } = useAuth();
  if (staff && auth && !isStaff) {
    return <><Nav /><main className="mx-auto max-w-md px-4 py-16"><LoginForm /></main></>;
  }
  return (
    <>
      <Nav />
      <main className={`mx-auto ${wide ? "max-w-[1600px]" : "max-w-[1300px]"} px-4 py-6`}>
        {(title || actions) && (
          <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
            {title && <h1 className="text-2xl font-bold">{title}</h1>}
            <div className="flex gap-2 flex-wrap">{actions}</div>
          </div>
        )}
        {children}
      </main>
    </>
  );
}

export function LoginForm({ onDone }: { onDone?: () => void }) {
  const { reloadAuth } = useAuth();
  const [pw, setPw] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <form className="card p-6 space-y-4" onSubmit={async (e) => {
      e.preventDefault();
      setBusy(true); setErr(null);
      try {
        await api("/api/auth/login", { json: { password: pw } });
        reloadAuth();
        if (onDone) onDone(); else window.location.reload();   // re-run the page's data requests
      }
      catch { setErr("That password is not right."); }
      finally { setBusy(false); }
    }}>
      <h1 className="text-2xl font-bold">Staff login</h1>
      <p className="text-muted text-sm">Hunt, Course Setup and Admin are for booth staff.</p>
      <input className="input text-lg" type="password" autoFocus placeholder="Staff password" value={pw} onChange={(e) => setPw(e.target.value)} />
      <button className="btn btn-primary" disabled={!pw || busy}>{busy ? "Checking..." : "Log in"}</button>
      <ErrorBox error={err} />
    </form>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div className="flex gap-1 border-b border-line mb-5 overflow-x-auto">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)}
          className={`px-4 py-2 font-semibold border-b-2 -mb-px whitespace-nowrap ${value === t.id ? "border-brand text-text" : "border-transparent text-muted hover:text-text"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Stat({ label, value, sub, big }: { label: string; value: React.ReactNode; sub?: React.ReactNode; big?: boolean }) {
  return (
    <div className="card p-4">
      <div className="label">{label}</div>
      <div className={`${big ? "text-5xl" : "text-2xl"} font-bold tabular mt-1`}>{value}</div>
      {sub && <div className="text-sm text-muted mt-1">{sub}</div>}
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  const color: Record<string, string> = {
    out: "var(--accent)", processing: "var(--brand)", needs_review: "var(--bad)", published: "var(--good)",
    error: "var(--bad)", draft: "var(--muted)", archived: "var(--muted)", parsed: "var(--good)", ready: "var(--good)",
    matched: "var(--good)", review: "var(--warn)", stray: "var(--muted)", reserved: "var(--muted)", unidentified: "var(--muted)",
  };
  const label: Record<string, string> = { out: "out on course", needs_review: "needs review" };
  return <span className="pill" style={{ color: color[status] || "var(--muted)", borderColor: color[status] || "var(--line)" }}>{label[status] || status}</span>;
}

export function ErrorBox({ error }: { error: string | null | undefined }) {
  if (!error) return null;
  return <div className="card p-3 border-bad text-bad my-3">{error}</div>;
}
