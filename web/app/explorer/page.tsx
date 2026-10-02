"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBox, Page, StatusPill } from "@/components/Nav";
import { upload, useApi } from "@/lib/api";
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
  const library = recs.data?.filter((r) => r.in_library) || [];
  const others = recs.data?.filter((r) => !r.in_library) || [];

  const go = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("title", title); fd.append("description", desc);
      fd.append("profile", profile); fd.append("in_library", String(save));
      const r = await upload("/api/recordings", fd);
      router.push(`/explorer/${r.id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

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
          <button className="btn btn-primary" disabled={!file || busy} onClick={go}>{busy ? "Reading file..." : "Analyze"}</button>
          <ErrorBox error={err} />
        </div>
        <div className="card p-6">
          <h2 className="text-xl font-bold mb-3">Recent uploads</h2>
          {others.map((r) => (
            <div key={r.id} className="flex justify-between py-2 border-b border-line">
              <Link href={`/explorer/${r.id}`} className="font-semibold hover:text-brand">{r.title}</Link>
              <StatusPill status={r.status} />
            </div>
          ))}
          {!others.length && <div className="text-muted">None yet.</div>}
        </div>
      </div>}
    </Page>
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
