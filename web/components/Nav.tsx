"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Wordmark from "./Wordmark";

const ITEMS = [
  { href: "/display", label: "Display" },
  { href: "/hunt", label: "Hunt" },
  { href: "/course", label: "Course Setup" },
  { href: "/explorer", label: "Recording Explorer" },
  { href: "/admin", label: "Admin" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="border-b border-line bg-panel sticky top-0 z-30">
      <div className="mx-auto max-w-[1600px] px-4 flex items-center gap-6 h-14">
        <Link href="/" className="flex items-center"><Wordmark /></Link>
        <nav className="flex gap-1 overflow-x-auto">
          {ITEMS.map((i) => {
            const on = path === i.href || path.startsWith(i.href + "/");
            return (
              <Link key={i.href} href={i.href}
                className={`px-3 py-2 rounded-md font-semibold whitespace-nowrap ${on ? "bg-brand text-black" : "text-muted hover:text-text"}`}>
                {i.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

export function Page({ title, actions, children, wide }: { title?: string; actions?: React.ReactNode; children: React.ReactNode; wide?: boolean }) {
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
