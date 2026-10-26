"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorBox, Page, StatusPill } from "@/components/Nav";
import { api, uploadRecording, UploadProgress, useApi } from "@/lib/api";
import { useAuth } from "@/components/BrandProvider";
import { fmtTime } from "@/lib/format";

export default function Explorer() {
  const router = useRouter();
  const recs = useApi<any[]>("/api/recordings", ["recording"]);
  const { isStaff } = useAuth();
  const profiles = useApi<any[]>("/api/profiles");
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [profile, setProfile] = useState("generic");
  const [save, setSave] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [prog, setProg] = useState<UploadProgress | null>(null);
  const live = recs.data?.filter((r) => !r.archived) || [];
  const library = live.filter((r) => r.in_library);
  const others = live.filter((r) => !r.in_library);
  const old = recs.data?.filter((r) => r.archived) || [];
  const setArchived = async (r: any, archived: boolean) => {
    await api(`/api/recordings/${r.id}`, { method: "PATCH", json: { archived } });
    recs.reload();
  };

  const go = async () => {
    if (!file) return;
    setBusy(true); setErr(null); setProg(null);
    try {
      const id = await uploadRecording(file, { title, description: desc, profile, in_library: save }, setProg);
      router.push(`/explorer/${id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); setProg(null); }
  };

  // Closing the tab mid-upload would stop it (once it is on the server, it finishes on its own)
  useEffect(() => {
    if (prog?.phase !== "upload") return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [prog?.phase]);

  return (
    <Page title="Recording Explorer">
      <h2 className="text-xl font-bold mb-3">Demo Library</h2>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        {library.map((r) => <RecCard key={r.id} r={r} />)}
        {!library.length && <div className="text-muted">The library is empty. The drone flight loads automatically when fixtures/Drone_Flight.IDE is present.</div>}
      </div>
      {isStaff && <div className="grid lg:grid-cols-2 gap-6">
        <div className="card p-6 space-y-3">
          <h2 className="text-xl font-bold">Open a recording</h2>
          <div className={`border-2 border-dashed rounded-lg p-6 text-center ${file ? "border-brand" : "border-line"}`}
            onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); setFile(e.dataTransfer.files[0]); }}>
            {file ? file.name : <span className="text-muted">Drop any .IDE file here</span>}
            <label className="btn mt-3 ml-3">Choose<input type="file" className="hidden" accept=".ide,.IDE,.zip" onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
          </div>
          <input className="input" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea className="input" placeholder="Short description" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <select className="input" value={profile} onChange={(e) => setProfile(e.target.value)}>
            {profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}: {p.description}</option>)}
          </select>
          <label className="flex gap-2 items-center"><input type="checkbox" checked={save} onChange={(e) => setSave(e.target.checked)} /> Save to the Demo Library</label>
          {file && <div className="text-sm text-muted">{fmtSize(file.size)}{file.size > 150e6 ? ": a long recording. Uploading and reading it takes a few minutes." : ""}</div>}
          <button className="btn btn-primary" disabled={!file || busy} onClick={go}>{busy ? (prog?.phase === "processing" ? "Reading recording..." : "Uploading...") : "Analyze"}</button>
          {busy && prog && <UploadBar p={prog} />}
          <ErrorBox error={err} />
        </div>
        <div className="card p-6">
          <h2 className="text-xl font-bold mb-3">Recent uploads</h2>
          {others.map((r) => (
            <div key={r.id} className="flex justify-between items-center gap-2 py-2 border-b border-line">
              <Link href={`/explorer/${r.id}`} className="font-semibold hover:text-brand flex-1">{r.title}</Link>
              <StatusPill status={r.status} />
              <button className="btn text-xs py-1" title="Move to Old recordings (can be restored)" onClick={() => setArchived(r, true)}>Archive</button>
            </div>
          ))}
          {!others.length && <div className="text-muted">None yet.</div>}
          {old.length > 0 && (
            <details className="mt-5">
              <summary className="cursor-pointer label">Old recordings ({old.length})</summary>
              {old.map((r) => (
                <div key={r.id} className="flex justify-between items-center gap-2 py-2 border-b border-line text-muted">
                  <Link href={`/explorer/${r.id}`} className="hover:text-brand flex-1">{r.title}</Link>
                  <button className="btn text-xs py-1" onClick={() => setArchived(r, false)}>Restore</button>
                </div>
              ))}
            </details>
          )}
        </div>
      </div>}
    </Page>
  );
}

function fmtSize(b: number) {
  return b >= 1e9 ? `${(b / 1e9).toFixed(2)} GB` : b >= 1e6 ? `${(b / 1e6).toFixed(0)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`;
}

function UploadBar({ p }: { p: UploadProgress }) {
  const pct = Math.round(p.fraction * 100);
  return (
    <div className="space-y-1">
      <div className="h-2 rounded bg-panel-2 overflow-hidden">
        <div className={`h-full transition-all ${p.phase === "processing" ? "bg-accent" : "bg-brand"}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-sm text-muted">
        {p.phase === "upload"
          ? (p.retrying ? `Connection dropped at ${pct}%, retrying...` : `Uploading ${pct}%. Keep this tab open until the upload finishes.`)
          : `Reading the recording ${pct}%. The upload is done: you can leave this page; it appears under Recent uploads when ready.`}
      </div>
    </div>
  );
}

function RecCard({ r }: { r: any }) {
  return (
    <Link href={`/explorer/${r.id}`} className="card p-5 hover:border-brand">
      <div className="flex justify-between items-start gap-2">
        <div className="text-xl font-bold">{r.title}</div>
        <StatusPill status={r.status} />
      </div>
      <div className="text-sm text-muted mt-1">{r.upload?.model} · sensor {r.upload?.serial} · {fmtTime(r.upload?.duration_s, 0)} · {r.profile} profile</div>
      {r.description && <div className="mt-2 text-sm">{r.description}</div>}
    </Link>
  );
}
