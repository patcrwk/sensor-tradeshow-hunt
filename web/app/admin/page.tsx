"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useSettings } from "@/components/BrandProvider";
import { ErrorBox, Page } from "@/components/Nav";
import { api, apiBase, useApi } from "@/lib/api";
import QrCode, { originUrl } from "@/components/QrCode";
import { DownloadQrButton, planSigns } from "@/components/SignSheet";

const PANEL_OPTIONS = [
  ["join", "How to play (invites passers-by to join)"],
  ["leaderboard:fastest", "Leaderboard: fastest"], ["leaderboard:efficient", "Leaderboard: most efficient"],
  ["leaderboard:crew", "Leaderboard: beat the crew"], ["leaderboard:steady", "Leaderboard: steadiest hands"],
  ["leaderboard:steps", "Leaderboard: most steps"], ["leaderboard:cadence", "Leaderboard: highest cadence"],
  ["leaderboard:speed", "Leaderboard: top speed"], ["crowd", "Crowd stats and finishing times"],
  ["heatmap", "Heat map of all tracks"], ["environment", "Show-floor environment map"],
  ["course", "Course map"], ["story:library", "Recording stories (Demo Library)"],
];

export default function Admin() {
  const { settings, reload } = useSettings();
  const [s, setS] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const review = useApi<any[]>("/api/runs?status=needs_review", ["run"]);
  const courses = useApi<any[]>("/api/courses", ["course"]);
  const library = useApi<any[]>("/api/recordings?library=true", ["recording"]);
  const health = useApi<any>("/api/health", [], 5000);
  const auditLog = useApi<any[]>("/api/admin/audit?limit=40", ["run", "course"]);
  useEffect(() => { if (settings && !s) setS(JSON.parse(JSON.stringify(settings))); }, [settings, s]);
  if (!s) return <Page staff title="Admin">Loading...</Page>;

  const save = async (patch: any) => {
    setErr(null); setMsg(null);
    try { await api("/api/settings", { method: "PUT", json: patch }); reload(); setMsg("Saved."); } catch (e: any) { setErr(e.message); }
  };
  const b = s.branding, k = s.kiosk;

  return (
    <Page staff title="Admin">
      {msg && <div className="text-good mb-3">{msg}</div>}
      <ErrorBox error={err} />
      <div className="grid lg:grid-cols-2 gap-6">
        <section className="card p-5 space-y-3">
          <h2 className="text-xl font-bold">Event and branding</h2>
          <Field label="Event name (big screen)" value={b.event_name} onChange={(v) => setS({ ...s, branding: { ...b, event_name: v } })} />
          <div className="grid grid-cols-[1fr_2fr] gap-3">
            <Field label="Short name (wordmark)" value={b.company} onChange={(v) => setS({ ...s, branding: { ...b, company: v } })} />
            <Field label="Full company name" value={b.company_full || ""} onChange={(v) => setS({ ...s, branding: { ...b, company_full: v } })} />
          </div>
          <Field label="Tagline" value={b.tagline} onChange={(v) => setS({ ...s, branding: { ...b, tagline: v } })} />
          <div className="pt-2 border-t border-line label">Printed signs</div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Booth" value={b.booth_label ?? "BOOTH 616"} onChange={(v) => setS({ ...s, branding: { ...b, booth_label: v } })} />
            <Field label="Website" value={b.website ?? "www.bigduckappliedsciences.com"} onChange={(v) => setS({ ...s, branding: { ...b, website: v } })} />
            <Field label="Start/finish called" value={b.home_term ?? "Home Base"} onChange={(v) => setS({ ...s, branding: { ...b, home_term: v } })} />
            <Field label="Stations called" value={b.station_term ?? "Waypoint"} onChange={(v) => setS({ ...s, branding: { ...b, station_term: v } })} />
          </div>
          <Field label="Sign footer" value={b.sign_footer ?? "Join the scavenger hunt and see your own live telemetry!"} onChange={(v) => setS({ ...s, branding: { ...b, sign_footer: v } })} />
          <Field label="Logo URL (optional; put files in web/public and use /logo.png)" value={b.logo_url || ""} onChange={(v) => setS({ ...s, branding: { ...b, logo_url: v || null } })} />
          <div className="grid grid-cols-2 gap-3">
            <label><div className="label mb-1">Primary color</div><input type="color" className="w-full h-10" value={b.primary} onChange={(e) => setS({ ...s, branding: { ...b, primary: e.target.value } })} /></label>
            <label><div className="label mb-1">Accent color</div><input type="color" className="w-full h-10" value={b.accent} onChange={(e) => setS({ ...s, branding: { ...b, accent: e.target.value } })} /></label>
          </div>
          <button className="btn btn-primary" onClick={() => save({ branding: s.branding })}>Save branding</button>
        </section>

        <section className="card p-5 space-y-3">
          <h2 className="text-xl font-bold">Kiosk rotation</h2>
          <div className="text-sm text-muted">Open <Link className="text-brand" href="/display">/display</Link> on the big monitor (or run <code>make kiosk</code>). No mouse needed.</div>
          <div className="space-y-1">
            {PANEL_OPTIONS.map(([id, label]) => (
              <label key={id} className="flex gap-2 items-center">
                <input type="checkbox" checked={k.panels.includes(id)} onChange={(e) => setS({ ...s, kiosk: { ...k, panels: e.target.checked ? [...k.panels, id] : k.panels.filter((x: string) => x !== id) } })} />
                {label}
              </label>
            ))}
          </div>
          <Field label="Seconds per panel" value={String(k.seconds_per_panel)} onChange={(v) => setS({ ...s, kiosk: { ...k, seconds_per_panel: Math.max(5, +v || 15) } })} />
          {library.data && library.data.length > 0 && (
            <div>
              <div className="label mb-1">Stories to show (none checked = all library recordings)</div>
              {library.data.map((r) => (
                <label key={r.id} className="flex gap-2 items-center">
                  <input type="checkbox" checked={k.story_recording_ids.includes(r.id)} onChange={(e) => setS({ ...s, kiosk: { ...k, story_recording_ids: e.target.checked ? [...k.story_recording_ids, r.id] : k.story_recording_ids.filter((x: number) => x !== r.id) } })} />
                  {r.title}
                </label>
              ))}
            </div>
          )}
          <button className="btn btn-primary" onClick={() => save({ kiosk: s.kiosk })}>Save rotation</button>
        </section>

        <section className="card p-5 space-y-3">
          <h2 className="text-xl font-bold">Hunt operations</h2>
          <div>
            <div className="label mb-1">Active course</div>
            <select className="input" value={s.active_course_id ?? ""} onChange={(e) => { setS({ ...s, active_course_id: e.target.value ? +e.target.value : null }); save({ active_course_id: e.target.value ? +e.target.value : 0 }); }}>
              <option value="">None (time START to FINISH only)</option>
              {courses.data?.filter((c) => c.status === "published").map((c) => <option key={c.id} value={c.id}>{c.name} v{c.version}</option>)}
            </select>
          </div>
          <Field label={`Watch folder (sensor mounts as a USB drive; glob allowed, e.g. /Volumes/*/${s.sensor_data_subdir})`} value={s.watch_folder}
            onChange={(v) => setS({ ...s, watch_folder: v })} />
          <div className="text-xs text-muted">Watcher: {health.data?.watcher?.folder ? `scanning ${health.data.watcher.folder}, ${health.data.watcher.found} file(s) found` : "off"}{health.data?.watcher?.error ? `; error: ${health.data.watcher.error}` : ""}</div>
          <label className="flex gap-2 items-center"><input type="checkbox" checked={s.auto_publish} onChange={(e) => setS({ ...s, auto_publish: e.target.checked })} />
            Publish clean runs to the display automatically (runs with problems always wait for review)</label>
          <div className="flex gap-2">
            <button className="btn btn-primary" onClick={() => save({ watch_folder: s.watch_folder, auto_publish: s.auto_publish })}>Save</button>
            <button className="btn" onClick={async () => { const r = await api("/api/admin/watch/scan", { method: "POST" }); setMsg(`Scan found ${r.new.length} new file(s).`); }}>Scan now</button>
          </div>
          <div className="pt-2 border-t border-line">
            <div className="font-semibold">Runs needing review: {review.data?.length ?? 0}</div>
            {review.data?.map((r) => <div key={r.id}><Link className="text-brand" href={`/hunt/runs/${r.id}`}>{r.name}</Link> <span className="text-muted text-sm">{r.error || ""}</span></div>)}
          </div>
        </section>

        <QrPrintBox activeId={s.active_course_id} />

        <section className="card p-5 space-y-3">
          <h2 className="text-xl font-bold">Leads and reset</h2>
          <a className="btn" href={`${apiBase()}/api/admin/leads.csv`}>Export leads CSV (consented only)</a>
          <div className="text-sm text-muted">Company and email are stored only when the participant consented, and never appear on the display.</div>
          <ResetBox onDone={() => { reload(); setMsg("Event reset. Participants, runs and GPS tracks deleted. Courses and the Demo Library are kept."); }} />
        </section>

        <SynthBox />

        <section className="card p-5">
          <h2 className="text-xl font-bold mb-2">Audit log</h2>
          <div className="max-h-80 overflow-auto text-sm space-y-1">
            {auditLog.data?.map((a) => <div key={a.id}><span className="text-muted">{new Date(a.at * 1000).toLocaleTimeString()}</span> {a.action}{a.run_id ? ` run ${a.run_id}` : ""}{a.course_id ? ` course ${a.course_id}` : ""}{a.note ? `: ${a.note.slice(0, 120)}` : ""}</div>)}
          </div>
        </section>
      </div>
    </Page>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return <label className="block"><div className="label mb-1">{label}</div><input className="input" value={value} onChange={(e) => onChange(e.target.value)} /></label>;
}

function ResetBox({ onDone }: { onDone: () => void }) {
  const [txt, setTxt] = useState("");
  const [name, setName] = useState("");
  return (
    <div className="border border-bad rounded-lg p-3 space-y-2">
      <div className="font-semibold text-bad">Reset event</div>
      <div className="text-sm text-muted">Deletes all participants, runs, participant recordings and GPS tracks for this event. Type RESET to confirm.</div>
      <input className="input" placeholder="New event name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
      <div className="flex gap-2">
        <input className="input" value={txt} onChange={(e) => setTxt(e.target.value)} placeholder="RESET" />
        <button className="btn btn-danger" disabled={txt !== "RESET"} onClick={async () => { await api("/api/admin/reset", { json: { confirm: txt, new_event_name: name || null } }); setTxt(""); onDone(); }}>Reset</button>
      </div>
    </div>
  );
}

function SynthBox() {
  const [gps, setGps] = useState("outdoor");
  const [holders, setHolders] = useState(false);
  const [taps, setTaps] = useState(false);
  const [serial, setSerial] = useState(90001);
  const [files, setFiles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  return (
    <section className="card p-5 space-y-3">
      <h2 className="text-xl font-bold">Synthetic test data</h2>
      <div className="text-sm text-muted">Generates a survey walk and three participant runs (one skips a station; each has a stray stop and a hand-held pause) for testing without real sensors. Participant serials start at the number below; check those serials out first, then upload the participant files on the Returns tab.</div>
      <div className="grid grid-cols-2 gap-3">
        <select className="input" value={gps} onChange={(e) => setGps(e.target.value)}>
          <option value="outdoor">GPS outdoor (2 to 5 m)</option><option value="indoor">GPS indoor, degraded</option>
          <option value="dropout">GPS dropouts</option><option value="none">No GPS</option>
        </select>
        <input className="input" type="number" value={serial} onChange={(e) => setSerial(+e.target.value)} />
      </div>
      <label className="flex gap-2 items-center"><input type="checkbox" checked={holders} onChange={(e) => setHolders(e.target.checked)} /> Stations use holders (orientation identity)</label>
      <label className="flex gap-2 items-center"><input type="checkbox" checked={taps} onChange={(e) => setTaps(e.target.checked)} /> Tap codes before each station rest</label>
      <button className="btn btn-primary" disabled={busy} onClick={async () => {
        setBusy(true);
        try { const r = await api("/api/admin/synthetic", { json: { kind: "set", gps_profile: gps, use_holders: holders, use_taps: taps, serial, seed: Math.floor(Math.random() * 1000) } }); setFiles(r.files); }
        finally { setBusy(false); }
      }}>{busy ? "Generating..." : "Generate files"}</button>
      {files.map((f) => <div key={f}><a className="text-brand text-sm" href={`${apiBase()}/api/admin/synthetic/${f.split("/").pop()}`}>{f.split("/").pop()}</a></div>)}
    </section>
  );
}


function QrPrintBox({ activeId }: { activeId: number | null }) {
  const { data: plan, reload } = useApi<any>("/api/qr/plan", ["course"]);
  const [count, setCount] = useState<string>("");
  const [names, setNames] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (!plan) return;
    setCount((c) => (c === "" ? String(plan.count || 6) : c));
    setNames((n) => ({ ...(plan.names || {}), ...n }));
  }, [plan]);
  const n = Math.max(0, Math.min(99, parseInt(count || "0") || 0));
  const codes: Record<string, string> = plan?.codes || {};
  const saved = plan && plan.count === n && Array.from({ length: n }, (_, k) => `S${k + 1}`).every((sid) => codes[sid])
    && Object.entries(names).every(([k, v]) => (plan.names?.[k] || "") === (v || ""));
  const ac = plan?.active_course;
  const local = typeof window !== "undefined" && /^(localhost|127\.|\[::1\])/.test(window.location.hostname);

  const save = async () => {
    setBusy(true); setErr(null);
    try { await api("/api/qr/plan", { method: "PUT", json: { count: n, names } }); reload(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <section className="card p-5 space-y-4 lg:col-span-2">
      <div>
        <h2 className="text-xl font-bold">Printable QR codes</h2>
        <p className="text-sm text-muted mt-1">
          Set how many stations you plan to have and generate the signs: one per station plus a START/FINISH sign for
          the booth. Print them before the show. When the crew walks the survey (stations in numbered order), the mapped
          course picks up these same codes, so the printed signs just work. Codes never change once made: adding
          stations adds signs, removing stations only hides them. Participant codes are personal and appear on screen at
          check-out.
        </p>
      </div>
      <div className="flex gap-3 items-end flex-wrap">
        <label><div className="label mb-1">Number of stations</div>
          <input className="input w-32 text-lg" type="number" min={1} max={99} value={count} onChange={(e) => setCount(e.target.value)} /></label>
        <button className="btn btn-primary" disabled={busy || n < 1 || !!saved} onClick={save}>
          {busy ? "Generating..." : plan?.count ? (saved ? "Codes up to date" : "Update codes") : "Generate codes"}</button>
        {plan?.count > 0 && <a className="btn" href="/admin/qr" target="_blank">Open printable signs ({plan.count + 1} pages)</a>}
        {plan?.count > 0 && <DownloadQrButton signs={planSigns(plan)} zipName="qr-codes.zip" />}
      </div>
      {n > 0 && (
        <details>
          <summary className="cursor-pointer label">Station names (optional, printed on the signs)</summary>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2 mt-2">
            {Array.from({ length: n }, (_, k) => `S${k + 1}`).map((sid, k) => (
              <label key={sid} className="flex items-center gap-2">
                <span className="w-8 text-right font-bold">{k + 1}</span>
                <input className="input py-1" placeholder={`Station ${k + 1}`} value={names[sid] || ""} onChange={(e) => setNames({ ...names, [sid]: e.target.value })} />
              </label>
            ))}
          </div>
        </details>
      )}
      {local && <div className="card p-3 border-warn text-warn text-sm">
        You are on {typeof window !== "undefined" ? window.location.host : "localhost"}. QR codes contain the address of this page, so
        signs printed here would send phones to your laptop. Print from the live site instead.</div>}
      {ac && (
        <div className="text-sm">
          Active course <b>{ac.name} v{ac.version}</b> has {ac.stations} stations.
          {plan?.count > 0 && ac.stations > plan.count && <span className="text-warn"> {ac.stations - plan.count} of them have no planned sign: raise the count and print the extra signs.</span>}
          {plan?.count > 0 && ac.stations < plan.count && <span className="text-warn"> The plan has {plan.count - ac.stations} more sign(s) than the course; those codes will not check in.</span>}
          {!ac.qr_on && <span className="text-warn"> QR check-ins are off for this course.</span>}
          {!ac.qr_on && <button className="btn text-sm ml-2" onClick={async () => {
            const c = await api(`/api/courses/${ac.id}`);
            await api(`/api/courses/${ac.id}`, { method: "PATCH", json: { identity_methods: [...(c.data.identity_methods || []), "qr"] } });
            reload();
          }}>Turn on QR check-ins</button>}
        </div>
      )}
      {!ac && plan?.count > 0 && <div className="text-sm text-muted">No course is published yet. That is fine: print now, and the course will use these codes once the survey is mapped and published.</div>}
      <ErrorBox error={err} />
      {plan?.count > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-8 gap-3">
          {["BOOTH", ...Array.from({ length: plan.count }, (_, k) => `S${k + 1}`)].filter((sid) => codes[sid]).map((sid) => (
            <div key={sid} className="text-center">
              <QrCode text={originUrl(`/s/${codes[sid]}`)} size={110} />
              <div className="text-xs mt-1 truncate">{sid === "BOOTH" ? "START / FINISH" : plan.names?.[sid] || `Station ${sid.slice(1)}`}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
