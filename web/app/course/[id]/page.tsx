"use client";
import { use, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import CourseMap, { RouteLegend } from "@/components/CourseMap";
import { ErrorBox, Page, StatusPill, Tabs } from "@/components/Nav";
import { api, apiBase, upload, useApi } from "@/lib/api";
import { fmtM, fmtTime, MODE_LABEL } from "@/lib/format";

const METHODS = [
  { id: "gps", label: "GPS position" },
  { id: "orientation", label: "Holder orientation" },
  { id: "taps", label: "Tap code" },
  { id: "beacon", label: "Vibration beacon" },
  { id: "qr", label: "QR code scans (participant phones)" },
];

export default function CoursePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { data: c, error, reload, setData } = useApi<any>(`/api/courses/${id}`, ["course"]);
  const [tab, setTab] = useState("map");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const patch = async (body: any) => {
    setErr(null);
    try { setData(await api(`/api/courses/${id}`, { method: "PATCH", json: body })); } catch (e: any) { setErr(e.message); }
  };

  if (error) return <Page staff title="Course"><ErrorBox error={error} /></Page>;
  if (!c) return <Page staff title="Course">Loading...</Page>;
  const d = c.data;
  const editable = c.status !== "published" && c.status !== "archived";

  return (
    <Page staff wide title={`${c.name} v${c.version}`} actions={
      <>
        <StatusPill status={c.status} />
        {c.active && <span className="pill" style={{ color: "var(--good)", borderColor: "var(--good)" }}>active course</span>}
        {editable && d && <button className="btn btn-primary" onClick={async () => {
          try {
            const r = await api(`/api/courses/${id}/publish`, { method: "POST" });
            reload();
            if (r.runs_to_rescore && confirm(`Course published. Re-score the ${r.runs_to_rescore} existing run(s) against this version?`)) {
              await api(`/api/courses/${id}/rescore`, { method: "POST" });
              setMsg("Re-scoring runs in the background.");
            }
          } catch (e: any) { setErr(e.message); }
        }}>Publish</button>}
        {!editable && <button className="btn" onClick={async () => { const n = await api(`/api/courses/${id}/new-version`, { method: "POST" }); router.push(`/course/${n.id}`); }}>Edit as new version</button>}
        {d?.qr_codes && <a className="btn" href={`/course/${id}/qr`} target="_blank">Print QR signs</a>}
        <a className="btn" href={`${apiBase()}/api/courses/${id}/export`}>Export package</a>
      </>}>
      <ErrorBox error={err || c.error} />
      {msg && <div className="text-good mb-3">{msg}</div>}
      {!d ? <div className="card p-6">
        <div className="text-bad font-bold mb-2">The survey could not be turned into a course.</div>
        <div className="text-muted">Check the survey walk followed the protocol (15 s rests at START, each station and FINISH). You can add another survey file below or re-run with a different mode.</div>
        <AddSurvey id={id} onDone={reload} />
      </div> : (
        <>
          <Quality q={d.quality} mode={d.positioning_mode} warnings={d.warnings} />
          <Tabs value={tab} onChange={setTab} tabs={[
            { id: "map", label: "Map and stations" }, { id: "rules", label: "Rules and identity" },
            { id: "legs", label: "Leg distances" }, { id: "background", label: "Background image" }, { id: "surveys", label: "Survey files" },
          ]} />
          {tab === "map" && <MapTab c={c} d={d} editable={editable} patch={patch} />}
          {tab === "rules" && <RulesTab d={d} editable={editable} patch={patch} rederive={async (mode: string) => {
            try { setData(await api(`/api/courses/${id}/rederive`, { json: { mode } })); } catch (e: any) { setErr(e.message); }
          }} />}
          {tab === "legs" && <LegsTab d={d} />}
          {tab === "background" && <BackgroundTab c={c} d={d} onChange={setData} />}
          {tab === "surveys" && <div className="card p-4 space-y-2">
            {c.surveys.map((s: any) => <div key={s.id}>{s.filename} <span className="text-muted text-sm">sensor {s.serial}, {fmtTime(s.duration_s, 0)}, {s.has_gps ? "GPS" : "no GPS"}</span></div>)}
            {d.notes?.map((n: string, i: number) => <div key={i} className="text-warn text-sm">{n}</div>)}
            {editable && <AddSurvey id={id} onDone={reload} />}
          </div>}
        </>
      )}
    </Page>
  );
}

function AddSurvey({ id, onDone }: { id: string; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  return (
    <label className="btn mt-3">{busy ? "Adding..." : "Add another survey walk (averages station positions)"}
      <input type="file" multiple className="hidden" accept=".ide,.IDE,.zip" onChange={async (e) => {
        const fs = Array.from(e.target.files || []);
        if (!fs.length) return;
        setBusy(true);
        const fd = new FormData(); fs.forEach((f) => fd.append("files", f));
        try { await upload(`/api/courses/${id}/surveys`, fd); } finally { setBusy(false); onDone(); }
      }} />
    </label>
  );
}

function Quality({ q, mode, warnings }: { q: any; mode: string; warnings: string[] }) {
  const color = { good: "var(--good)", fair: "var(--warn)", poor: "var(--bad)" }[q.level as string];
  return (
    <div className="card p-5 mb-5" style={{ borderColor: color }}>
      <div className="flex flex-wrap gap-8 items-center">
        <div>
          <div className="label">Venue GPS quality</div>
          <div className="text-4xl font-black uppercase" style={{ color }}>{q.level}</div>
        </div>
        <div><div className="label">Fix available</div><div className="text-2xl font-bold">{q.has_gps ? `${Math.round(q.fix_availability * 100)}%` : "no GPS"}</div><div className="text-xs text-muted">of the survey walk</div></div>
        <div><div className="label">Station accuracy</div><div className="text-2xl font-bold">{q.typical_station_accuracy_m != null ? `${q.typical_station_accuracy_m} m` : "--"}</div><div className="text-xs text-muted">95% radius, typical</div></div>
        <div><div className="label">Satellites / HDOP</div><div className="text-2xl font-bold">{q.median_satellites ?? "--"} / {q.median_hdop ?? "--"}</div></div>
        <div><div className="label">Recommended</div><div className="text-2xl font-bold">{MODE_LABEL[q.recommended_mode]}</div><div className="text-xs text-muted">match radius {q.recommended_radius_m} m</div></div>
        <div><div className="label">This course runs in</div><div className="text-2xl font-bold text-brand">{MODE_LABEL[mode]}</div></div>
      </div>
      <div className="text-muted mt-3">{q.explanation}.</div>
      {warnings?.map((w, i) => <div key={i} className="text-warn text-sm mt-1">Warning: {w}</div>)}
    </div>
  );
}

function MapTab({ c, d, editable, patch }: { c: any; d: any; editable: boolean; patch: (b: any) => void }) {
  return (
    <div className="grid xl:grid-cols-[3fr_2fr] gap-6">
      <div className="card p-4">
        <CourseMap courseId={c.id} booth={d.booth} stations={d.stations} background={d.background}
          reference={{ x: d.route.x, y: d.route.y, source: d.route.source, opacity: 0.8 }}
          matchRadius={d.identity_methods.includes("gps") ? d.match_radius_m : null} showAccuracy editable={editable}
          onStationMove={(sid, x, y) => patch({ stations: [{ id: sid, x, y }] })} />
        <div className="mt-2"><RouteLegend /></div>
        {editable && <div className="text-sm text-muted mt-1">Drag a station to correct its position. Shaded circles show each station's measured accuracy; dashed circles show the matching radius.</div>}
      </div>
      <div className="card p-4">
        <h2 className="text-xl font-bold mb-2">Stations</h2>
        <table className="grid-table text-sm">
          <thead><tr><th>#</th><th>Name</th><th>Position (m)</th><th>Accuracy</th><th>Tap / pose</th><th>Required</th></tr></thead>
          <tbody>
            {d.stations.map((s: any) => (
              <tr key={s.id}>
                <td className="font-bold">{s.number}</td>
                <td><input className="input py-1" defaultValue={s.name} disabled={!editable}
                  onBlur={(e) => e.target.value !== s.name && patch({ stations: [{ id: s.id, name: e.target.value }] })} /></td>
                <td className="tabular" title={s.lat ? `${s.lat.toFixed(6)}, ${s.lon.toFixed(6)}` : ""}>{s.x.toFixed(1)}, {s.y.toFixed(1)}{s.edited && <span className="text-warn"> moved</span>}</td>
                <td>{s.accuracy_m != null ? `${s.accuracy_m} m` : "--"}<div className="text-xs text-muted">{s.gps_fixes} fixes</div></td>
                <td className="text-xs">{s.tap_count ? `${s.tap_count} taps` : ""}{s.reserved_pose ? " flat" : ` [${s.orientation.map((v: number) => v.toFixed(1)).join(",")}]`}{s.beacon_hz ? ` ${s.beacon_hz} Hz` : ""}</td>
                <td><select className="input py-1" value={s.required === false ? "bonus" : "required"} disabled={!editable}
                  onChange={(e) => patch({ stations: [{ id: s.id, required: e.target.value === "required" }] })}>
                  <option value="required">required</option><option value="bonus">bonus</option></select></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
          <div><div className="label">Crew par</div><div className="text-2xl font-bold">{fmtTime(d.par.par_time_s, 0)}</div>
            <div className="text-xs text-muted">survey {fmtTime(d.par.survey_walk_s, 0)} minus {d.par.extra_rest_trimmed_s} s extra rest</div></div>
          <div><div className="label">Reference route</div><div className="text-2xl font-bold">{fmtM(d.walked.reduce((a: number, w: any) => a + w.meters, 0))}</div>
            <div className="text-xs text-muted">{d.steps.count} steps in the survey</div></div>
        </div>
        {d.dead_reckoning && <div className="text-sm text-muted mt-3">Dead-reckoning loop closure error {d.dead_reckoning.closure_error_m} m ({d.dead_reckoning.closure_error_pct}%), spread back along the route.{d.dead_reckoning.aligned_to_gps ? " Rotated to match the stations that had GPS." : ""}</div>}
      </div>
    </div>
  );
}

function RulesTab({ d, editable, patch, rederive }: { d: any; editable: boolean; patch: (b: any) => void; rederive: (m: string) => void }) {
  return (
    <div className="grid lg:grid-cols-2 gap-6">
      <div className="card p-5 space-y-4">
        <h2 className="text-xl font-bold">Rules</h2>
        <div>
          <div className="label mb-1">Station order</div>
          <select className="input" value={d.order_rule} disabled={!editable} onChange={(e) => patch({ order_rule: e.target.value })}>
            <option value="any">Any order</option><option value="fixed">Fixed order (by station number)</option>
          </select>
        </div>
        <div>
          <div className="label mb-1">Crew par time (seconds)</div>
          <input className="input" type="number" defaultValue={d.par.par_time_s} disabled={!editable} onBlur={(e) => patch({ par_time_s: +e.target.value })} />
        </div>
        <div>
          <div className="label mb-1">Positioning mode</div>
          <select className="input" value={d.positioning_mode} disabled={!editable} onChange={(e) => patch({ positioning_mode: e.target.value })}>
            <option value="gps">GPS</option><option value="fused">GPS + steps (fused)</option><option value="dead_reckoning">Dead reckoning (anchored to stations)</option>
          </select>
          {editable && <button className="btn text-sm mt-2" onClick={() => rederive(d.positioning_mode)}>Re-map stations and route in this mode</button>}
          <div className="text-xs text-muted mt-1">Changing the mode only changes how participant routes are drawn. Re-mapping recomputes station positions from the survey (edits are reset).</div>
        </div>
      </div>
      <div className="card p-5 space-y-4">
        <h2 className="text-xl font-bold">Station identity</h2>
        <div className="text-sm text-muted">When two or more methods are on, they must agree, or the check-in is flagged for review.</div>
        {METHODS.map((m) => (
          <label key={m.id} className="flex items-center gap-3">
            <input type="checkbox" className="w-5 h-5" disabled={!editable} checked={d.identity_methods.includes(m.id)}
              onChange={(e) => patch({ identity_methods: e.target.checked ? [...d.identity_methods, m.id] : d.identity_methods.filter((x: string) => x !== m.id) })} />
            <span className="font-semibold">{m.label}</span>
            {m.id === "beacon" && <span className="text-xs text-muted">needs 1000 Hz accel; tone pages at /beacon/&lt;station&gt;</span>}
            {m.id === "qr" && <span className="text-xs text-muted">phones scan the printed sign; the sensor rest still proves the stop</span>}
          </label>
        ))}
        <div>
          <div className="label mb-1">GPS matching radius (m)</div>
          <input className="input" type="number" step="0.5" defaultValue={d.match_radius_m} disabled={!editable} onBlur={(e) => patch({ match_radius_m: +e.target.value })} />
          <div className="text-xs text-muted mt-1">Recommended {d.quality.recommended_radius_m} m from the measured station accuracy.</div>
        </div>
      </div>
    </div>
  );
}

function LegsTab({ d }: { d: any }) {
  const ids = ["BOOTH", ...d.stations.map((s: any) => s.id)];
  const name = (i: string) => (i === "BOOTH" ? "Booth" : d.stations.find((s: any) => s.id === i)?.number);
  const lk: Record<string, any> = {};
  d.legs.forEach((l: any) => (lk[`${l.from}|${l.to}`] = l));
  return (
    <div className="card p-4 overflow-x-auto">
      <div className="text-sm text-muted mb-3">Meters along the walked route. <b className="text-text">Bold</b> legs were walked in the survey; others are straight line times the detour factor {d.detour_factor} learned from the walked legs.</div>
      <table className="grid-table tabular">
        <thead><tr><th>from \ to</th>{ids.map((i) => <th key={i}>{name(i)}</th>)}</tr></thead>
        <tbody>
          {ids.map((a) => (
            <tr key={a}><td className="font-bold">{name(a)}</td>
              {ids.map((b) => { const l = lk[`${a}|${b}`]; return <td key={b} className={l?.kind === "walked" ? "font-bold" : "text-muted"}>{l ? l.meters.toFixed(0) : ""}</td>; })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BackgroundTab({ c, d, onChange }: { c: any; d: any; onChange: (x: any) => void }) {
  const bg = d.background;
  const imgRef = useRef<HTMLImageElement>(null);
  const [pinFor, setPinFor] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const [ver, setVer] = useState(0);
  const pins: any[] = bg?.pins || [];
  const savePins = async (next: any[]) => {
    setErr(null);
    const im = imgRef.current;
    try { onChange(await api(`/api/courses/${c.id}/pins`, { method: "PUT", json: { pins: next, width: im?.naturalWidth, height: im?.naturalHeight } })); }
    catch (e: any) { setErr(e.message); }
  };
  return (
    <div className="grid xl:grid-cols-2 gap-6">
      <div className="card p-4 space-y-3">
        <h2 className="text-xl font-bold">Floor plan or venue image (optional)</h2>
        <label className="btn">Upload image<input type="file" accept="image/*" className="hidden" onChange={async (e) => {
          const f = e.target.files?.[0]; if (!f) return;
          const fd = new FormData(); fd.append("file", f);
          onChange(await upload(`/api/courses/${c.id}/background`, fd)); setVer((v) => v + 1);
        }} /></label>
        {bg && <>
          <div className="text-sm text-muted">Pick a station, then click where it is on the image. Pin two or more (three or more allows a full affine fit).</div>
          <select className="input" value={pinFor} onChange={(e) => setPinFor(e.target.value)}>
            <option value="">Choose a station to pin...</option>
            <option value="BOOTH">Booth</option>
            {d.stations.map((s: any) => <option key={s.id} value={s.id}>{s.number}. {s.name}</option>)}
          </select>
          <div className="relative">
            <img ref={imgRef} src={`${apiBase()}/api/courses/${c.id}/background?v=${ver}`} alt="background" className="w-full rounded cursor-crosshair"
              onClick={(e) => {
                if (!pinFor) return;
                const r = (e.target as HTMLImageElement).getBoundingClientRect();
                const im = imgRef.current!;
                const u = ((e.clientX - r.left) / r.width) * im.naturalWidth;
                const v = ((e.clientY - r.top) / r.height) * im.naturalHeight;
                savePins([...pins.filter((p) => p.station !== pinFor), { station: pinFor, u, v }]);
                setPinFor("");
              }} />
            {pins.map((p) => {
              const im = imgRef.current;
              if (!im?.naturalWidth) return null;
              return <div key={p.station} className="absolute -translate-x-1/2 -translate-y-1/2 bg-accent text-black font-bold rounded-full px-2 text-xs pointer-events-none"
                style={{ left: `${(p.u / im.naturalWidth) * 100}%`, top: `${(p.v / im.naturalHeight) * 100}%` }}>{p.station === "BOOTH" ? "B" : p.station.slice(1)}</div>;
            })}
          </div>
          <div className="text-sm">{pins.length} pin(s). {bg.transform ? `Fit: ${bg.transform.kind}, residual ${bg.transform.rms_px} px.` : "Needs at least two pins."}
            {pins.length > 0 && <button className="btn text-sm ml-2" onClick={() => savePins([])}>Clear pins</button>}</div>
          <ErrorBox error={err} />
        </>}
      </div>
      <div className="card p-4">
        <h2 className="text-xl font-bold mb-2">Preview</h2>
        <CourseMap courseId={c.id} booth={d.booth} stations={d.stations} background={bg}
          reference={{ x: d.route.x, y: d.route.y, source: d.route.source, opacity: 0.8 }} />
      </div>
    </div>
  );
}
