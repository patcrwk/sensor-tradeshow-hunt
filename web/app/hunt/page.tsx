"use client";
import Link from "next/link";
import { useState } from "react";
import { ErrorBox, Page, StatusPill, Tabs } from "@/components/Nav";
import Leaderboard from "@/components/Leaderboard";
import { api, upload, useApi } from "@/lib/api";
import { fmtAgo, fmtClock, fmtTime, MODE_LABEL } from "@/lib/format";

export default function HuntPage() {
  const [tab, setTab] = useState("checkout");
  return (
    <Page title="Hunt" wide>
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "checkout", label: "Check-out" }, { id: "returns", label: "Returns" },
        { id: "runs", label: "Runs" }, { id: "boards", label: "Leaderboards" },
      ]} />
      {tab === "checkout" && <Checkout />}
      {tab === "returns" && <Returns />}
      {tab === "runs" && <Runs />}
      {tab === "boards" && <Boards />}
    </Page>
  );
}

function Checkout() {
  const [name, setName] = useState("");
  const [serial, setSerial] = useState("");
  const [consent, setConsent] = useState(false);
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const sensors = useApi<any[]>("/api/sensors", ["run"]);
  const status = useApi<any>(serial ? `/api/sensors/${encodeURIComponent(serial)}/status` : null);
  const open = useApi<any[]>("/api/runs?status=out", ["run", "reset"]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      const r = await api("/api/runs/checkout", { json: { display_name: name, serial, consent, company, email } });
      setMsg(`${r.run.name} is out with sensor ${r.run.serial}.${r.warning ? " Note: " + r.warning : ""}`);
      setName(""); setSerial(""); setConsent(false); setCompany(""); setEmail("");
      open.reload();
    } catch (ex: any) { setErr(ex.message); }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <form onSubmit={submit} className="card p-6 space-y-4">
        <h2 className="text-xl font-bold">Check out a sensor</h2>
        <div>
          <div className="label mb-1">Display name (shown on the big screen)</div>
          <input className="input text-xl" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoFocus />
        </div>
        <div>
          <div className="label mb-1">Sensor serial (type or scan)</div>
          <input className="input text-xl tabular" list="sensor-list" value={serial} onChange={(e) => setSerial(e.target.value.trim())} required />
          <datalist id="sensor-list">
            {sensors.data?.filter((s) => !s.checked_out).map((s) => <option key={s.serial} value={s.serial}>{s.model || ""}</option>)}
          </datalist>
          {serial && status.data && (
            <div className="text-sm mt-2 text-warn">
              {status.data.has_gps === false ? "This sensor has recorded no GPS before. Check it is a GPS model. " : ""}
              {status.data.message}
            </div>
          )}
        </div>
        <label className="flex items-center gap-3">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="w-5 h-5" />
          <span>Participant agrees to be contacted (optional lead capture)</span>
        </label>
        {consent && (
          <div className="grid grid-cols-2 gap-3">
            <div><div className="label mb-1">Company</div><input className="input" value={company} onChange={(e) => setCompany(e.target.value)} /></div>
            <div><div className="label mb-1">Email</div><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          </div>
        )}
        <button className="btn btn-primary text-lg" disabled={!name || !serial}>Check out</button>
        {msg && <div className="text-good">{msg}</div>}
        <ErrorBox error={err} />
        <div className="text-sm text-muted border-t border-line pt-3">
          Tell the participant: at each station, set the sensor down and leave it still for 10 seconds. Start and finish
          the same way at the booth marker.
        </div>
      </form>
      <div className="card p-6">
        <h2 className="text-xl font-bold mb-3">Out on the course ({open.data?.length ?? 0})</h2>
        <table className="grid-table">
          <thead><tr><th>Name</th><th>Sensor</th><th>Out since</th><th></th></tr></thead>
          <tbody>
            {open.data?.map((r) => (
              <tr key={r.id}>
                <td className="font-semibold">{r.name}</td>
                <td className="tabular">{r.serial}</td>
                <td>{fmtClock(r.checkout_epoch)} <span className="text-muted text-sm">({fmtAgo(r.checkout_epoch)})</span></td>
                <td className="text-right">
                  <button className="btn btn-danger text-sm" onClick={async () => {
                    if (confirm(`Cancel the check-out for ${r.name}?`)) { await api(`/api/runs/${r.id}`, { method: "DELETE" }); open.reload(); }
                  }}>Cancel</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Returns() {
  const pending = useApi<any[]>("/api/uploads/pending", ["upload", "run", "reset"]);
  const open = useApi<any[]>("/api/runs?status=out", ["run"]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [over, setOver] = useState(false);

  const send = async (files: FileList | File[]) => {
    setBusy(true); setErr(null);
    for (const f of Array.from(files)) {
      try {
        const fd = new FormData();
        fd.append("file", f);
        const r = await upload("/api/uploads", fd);
        if (r.upload.status === "error") setErr(`${f.name}: ${r.upload.error}`);
        if (r.attached_run) setRecent((x) => [{ file: f.name, run: r.attached_run, note: "already processed" }, ...x]);
      } catch (e: any) { setErr(`${f.name}: ${e.message}`); }
    }
    setBusy(false);
    pending.reload();
  };

  return (
    <div className="space-y-6">
      <div className={`card p-10 text-center border-2 border-dashed ${over ? "border-brand" : "border-line"}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); send(e.dataTransfer.files); }}>
        <div className="text-2xl font-bold mb-2">{busy ? "Reading recording..." : "Drop the sensor's .IDE file here"}</div>
        <div className="text-muted mb-4">Or plug the sensor in: files in the watch folder (Admin) appear below automatically.</div>
        <label className="btn btn-primary">
          Choose file
          <input type="file" className="hidden" multiple accept=".ide,.IDE,.zip" onChange={(e) => e.target.files && send(e.target.files)} />
        </label>
      </div>
      <ErrorBox error={err} />
      {recent.map((r, i) => <div key={i} className="text-muted">{r.file}: {r.note}. <Link className="text-brand" href={`/hunt/runs/${r.run}`}>Open run</Link></div>)}
      <div>
        <h2 className="text-xl font-bold mb-3">Recordings waiting for a match ({pending.data?.length ?? 0})</h2>
        <div className="space-y-3">
          {pending.data?.map((p) => <PendingUpload key={p.upload.id} p={p} open={open.data || []} onDone={() => { pending.reload(); open.reload(); }} />)}
          {!pending.data?.length && <div className="text-muted">Nothing waiting.</div>}
        </div>
      </div>
    </div>
  );
}

function PendingUpload({ p, open, onDone }: { p: any; open: any[]; onDone: () => void }) {
  const u = p.upload;
  const best = p.candidates[0];
  const [choice, setChoice] = useState<number | "">(best?.id ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<number | null>(null);
  if (u.status === "error") {
    return <div className="card p-4 border-bad"><b>{u.filename}</b>: could not read the file. {u.error}</div>;
  }
  const confirmMatch = async () => {
    if (!choice) return;
    try {
      await api(`/api/runs/${choice}/attach`, { json: { upload_id: u.id } });
      setDone(choice as number);
      onDone();
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="card p-4 flex flex-wrap items-center gap-4">
      <div className="flex-1 min-w-[260px]">
        <div className="font-bold">{u.filename} {u.synthetic && <span className="pill ml-2 text-muted">synthetic</span>}</div>
        <div className="text-sm text-muted">
          Sensor {u.serial ?? "unknown"} · started {u.start_epoch ? new Date(u.start_epoch * 1000).toLocaleString() : "unknown"} · {fmtTime(u.duration_s, 0)} long · {u.has_gps ? "GPS recorded" : "no GPS"}
        </div>
        {best ? <div className="text-sm mt-1" style={{ color: best.score >= 1 ? "var(--good)" : "var(--warn)" }}>Best match: {best.name} ({best.reason})</div>
          : <div className="text-sm mt-1 text-warn">No open check-out for sensor {u.serial}. Pick one manually or check the sensor out first.</div>}
      </div>
      <select className="input w-64" value={choice} onChange={(e) => setChoice(e.target.value ? +e.target.value : "")}>
        <option value="">Choose a run...</option>
        {p.candidates.map((c: any) => <option key={c.id} value={c.id}>{c.name} (sensor {c.serial})</option>)}
        {open.filter((r) => !p.candidates.some((c: any) => c.id === r.id)).map((r) => <option key={r.id} value={r.id}>{r.name} (sensor {r.serial})</option>)}
      </select>
      <button className="btn btn-primary" disabled={!choice} onClick={confirmMatch}>Confirm match</button>
      {u.source_path && (
        <button className="btn btn-danger text-sm" onClick={async () => {
          if (confirm(`Delete ${u.source_path} from the sensor? This cannot be undone.`)) {
            try { await api(`/api/uploads/${u.id}/source?confirm=true`, { method: "DELETE" }); } catch (e: any) { setErr(e.message); }
          }
        }}>Clear from sensor</button>
      )}
      {done && <Link className="text-brand" href={`/hunt/runs/${done}`}>Open run</Link>}
      <ErrorBox error={err} />
    </div>
  );
}

function Runs() {
  const [filter, setFilter] = useState("");
  const runs = useApi<any[]>(`/api/runs${filter ? `?status=${filter}` : ""}`, ["run", "reset"]);
  return (
    <div className="card p-4">
      <div className="flex gap-2 mb-3 flex-wrap">
        {[["", "All"], ["needs_review", "Needs review"], ["processing", "Processing"], ["published", "Published"], ["out", "Out"]].map(([v, l]) => (
          <button key={v} className={`btn text-sm ${filter === v ? "btn-primary" : ""}`} onClick={() => setFilter(v)}>{l}</button>
        ))}
      </div>
      <table className="grid-table">
        <thead><tr><th>#</th><th>Name</th><th>Sensor</th><th>Status</th><th>Time</th><th>Stations</th><th>Position</th><th>Course</th><th></th></tr></thead>
        <tbody>
          {runs.data?.map((r) => (
            <tr key={r.id}>
              <td className="text-muted">{r.id}</td>
              <td className="font-semibold">{r.name}</td>
              <td className="tabular">{r.serial}</td>
              <td><StatusPill status={r.status} />{r.has_overrides && <span className="pill ml-1 text-muted">edited</span>}</td>
              <td className="tabular">{fmtTime(r.elapsed_s)}{r.elapsed_s != null && !r.complete && <span className="text-warn text-sm ml-1">incomplete</span>}</td>
              <td>{r.summary?.stations ?? "--"}{r.summary?.missing?.length ? <span className="text-warn text-sm"> ({r.summary.missing.length} missed)</span> : null}</td>
              <td className="text-sm">{r.positioning_mode ? MODE_LABEL[r.positioning_mode] : "--"}</td>
              <td className="text-sm text-muted">{r.course_id ? `#${r.course_id} v${r.course_version}` : "none"}</td>
              <td className="text-right">{r.status !== "out" && <Link className="btn text-sm" href={`/hunt/runs/${r.id}`}>Open</Link>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Boards() {
  const lbs = useApi<Record<string, any>>("/api/leaderboards", ["leaderboard", "reset"]);
  if (!lbs.data) return null;
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      {Object.entries(lbs.data).map(([k, v]) => <Leaderboard key={k} id={k} lb={v} link />)}
    </div>
  );
}
