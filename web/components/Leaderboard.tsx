"use client";
import Link from "next/link";
import { CATEGORY_FORMAT } from "@/lib/format";

export type LbRow = { rank: number; run_id: number; name: string; value: number; complete: boolean; stations: number; missing: number; mode?: string };
export type Lb = { title: string; desc: string; unit: string; rows: LbRow[] };

export default function Leaderboard({ id, lb, big, link, limit }: { id: string; lb: Lb | undefined; big?: boolean; link?: boolean; limit?: number }) {
  if (!lb) return null;
  const fmt = CATEGORY_FORMAT[id] || ((v: number) => String(v));
  const rows = lb.rows.slice(0, limit ?? lb.rows.length);
  return (
    <div className={big ? "" : "card p-4"}>
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className={`${big ? "text-6xl" : "text-xl"} font-extrabold`}>{lb.title}</h2>
        <div className={`${big ? "text-2xl" : "text-sm"} text-muted`}>{lb.desc}</div>
      </div>
      {!rows.length && <div className={`${big ? "text-3xl" : ""} text-muted py-6`}>No finishers yet. Be the first!</div>}
      <ol className="space-y-1">
        {rows.map((r) => {
          const inner = (
            <div className={`flex items-center gap-4 rounded-lg px-3 ${big ? "py-3 text-4xl" : "py-1.5 text-lg"} ${r.rank === 1 ? "bg-panel-2" : ""}`}>
              <span className={`w-12 text-right font-extrabold tabular ${r.rank <= 3 ? "text-accent" : "text-muted"}`}>{r.rank}</span>
              <span className="flex-1 font-bold truncate">{r.name}</span>
              {id === "fastest" && !r.complete && (
                <span className={`pill ${big ? "text-xl" : ""}`} style={{ color: "var(--warn)", borderColor: "var(--warn)" }}>
                  {r.missing ? `${r.missing} missed` : "incomplete"}
                </span>
              )}
              <span className="font-extrabold tabular">{fmt(r.value)}</span>
            </div>
          );
          return <li key={r.run_id}>{link ? <Link href={`/hunt/runs/${r.run_id}`}>{inner}</Link> : inner}</li>;
        })}
      </ol>
    </div>
  );
}
