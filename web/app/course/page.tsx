"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBox, Page, StatusPill } from "@/components/Nav";
import { upload, useApi } from "@/lib/api";
import { MODE_LABEL } from "@/lib/format";

export default function Courses() {
  const router = useRouter();
  const list = useApi<any[]>("/api/courses", ["course", "reset"]);
  const [name, setName] = useState("Main course");
  const [mode, setMode] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const create = async () => {
    setBusy(true); setErr(null);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      fd.append("name", name);
      if (mode) fd.append("mode", mode);
      const c = await upload("/api/courses/survey", fd);
      router.push(`/course/${c.id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const importPkg = async (f: File) => {
    setErr(null);
    try {
      const fd = new FormData(); fd.append("file", f);
      const c = await upload("/api/courses/import", fd);
      router.push(`/course/${c.id}`);
    } catch (e: any) { setErr(e.message); }
  };

  return (
    <Page staff title="Course Setup" actions={
      <label className="btn">Import course package<input type="file" accept=".zip" className="hidden" onChange={(e) => e.target.files?.[0] && importPkg(e.target.files[0])} /></label>
    }>
      <div className="grid lg:grid-cols-[2fr_3fr] gap-6">
        <div className="card p-6 space-y-4">
          <h2 className="text-xl font-bold">New course from a survey walk</h2>
          <ol className="text-sm text-muted list-decimal ml-5 space-y-1">
            <li>Place the station markers. Power on the survey sensor and wait for a GPS fix.</li>
            <li>Rest it at the booth START marker for 15 seconds.</li>
            <li>Walk to each station in numbered order and rest 15 to 20 seconds (tap the station number first if using tap codes; use the holder if using holders).</li>
            <li>Return and rest at FINISH for 15 seconds. Optional: a second walk in a different order improves accuracy.</li>
          </ol>
          <div><div className="label mb-1">Course name</div><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
          <div>
            <div className="label mb-1">Survey file(s)</div>
            <div className={`border-2 border-dashed rounded-lg p-6 text-center ${files.length ? "border-brand" : "border-line"}`}
              onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); setFiles(Array.from(e.dataTransfer.files)); }}>
              {files.length ? files.map((f) => <div key={f.name}>{f.name}</div>) : <span className="text-muted">Drop .IDE survey file(s) here</span>}
              <label className="btn mt-3">Choose<input type="file" multiple className="hidden" accept=".ide,.IDE,.zip" onChange={(e) => setFiles(Array.from(e.target.files || []))} /></label>
            </div>
          </div>
          <div>
            <div className="label mb-1">Positioning mode</div>
            <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="">Recommend from measured GPS quality</option>
              <option value="gps">GPS</option><option value="fused">GPS + steps (fused)</option><option value="dead_reckoning">Dead reckoning</option>
            </select>
          </div>
          <button className="btn btn-primary" disabled={!files.length || busy} onClick={create}>{busy ? "Mapping course..." : "Map the course"}</button>
          <ErrorBox error={err} />
        </div>
        <div className="card p-6">
          <h2 className="text-xl font-bold mb-3">Courses</h2>
          <table className="grid-table">
            <thead><tr><th>Name</th><th>Version</th><th>Status</th><th>Stations</th><th>Mode</th><th>GPS</th><th></th></tr></thead>
            <tbody>
              {list.data?.map((c) => (
                <tr key={c.id}>
                  <td className="font-semibold">{c.name} {c.active && <span className="pill ml-1" style={{ color: "var(--good)", borderColor: "var(--good)" }}>active</span>}</td>
                  <td>v{c.version}</td>
                  <td><StatusPill status={c.status} /></td>
                  <td>{c.stations ?? "--"}</td>
                  <td className="text-sm">{c.mode ? MODE_LABEL[c.mode] : "--"}</td>
                  <td className="text-sm">{c.quality ?? "--"}</td>
                  <td><Link href={`/course/${c.id}`} className="btn text-sm">Open</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!list.data?.length && <div className="text-muted py-4">No courses yet. Without a published course, runs are timed START to FINISH only.</div>}
        </div>
      </div>
    </Page>
  );
}
