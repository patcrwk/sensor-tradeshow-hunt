"use client";
import { use, useEffect, useMemo, useState } from "react";
import { ErrorBox, Page, Stat, StatusPill } from "@/components/Nav";
import Replay from "@/components/Replay";
import { RouteLegend } from "@/components/CourseMap";
import UPlotChart from "@/components/UPlotChart";
import { api, useApi } from "@/lib/api";
import { fmtDelta, fmtM, fmtNum, fmtTime, MODE_LABEL, SOURCE_LABEL } from "@/lib/format";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, reload } = useApi<any>(`/api/runs/${id}`, ["run"]);
  const course = useApi<any>(data?.run?.course_id ? `/api/courses/${data.run.course_id}` : null);
  const [ghostVs, setGhostVs] = useState<"" | "leader" | "crew">("");
  const ghost = useApi<any>(ghostVs ? `/api/runs/${id}/ghost?vs=${ghostVs}` : null);

  if (error) return <Page title="Run"><ErrorBox error={error} /></Page>;
  if (!data) return <Page title="Run">Loading...</Page>;
  const { run, result: res } = data;
  const cd = course.data?.data;

  return (
    <Page wide title={`${run.name}`} actions={
      <>
        <StatusPill status={run.status} />
        {run.status === "published"
          ? <button className="btn" onClick={async () => { await api(`/api/runs/${id}/unpublish`, { json: { note: "hidden from display" } }); reload(); }}>Hide from display</button>
          : run.upload_id && <button className="btn btn-primary" onClick={async () => { await api(`/api/runs/${id}/publish`, { json: { note: "published after review" } }); reload(); }}>Publish</button>}
        {run.upload_id && <button className="btn" onClick={async () => { await api(`/api/runs/${id}/reprocess`, { method: "POST" }); }}>Reprocess</button>}
      </>}>
      {run.error && <ErrorBox error={`Processing problem: ${run.error}. Fix check-ins below or reprocess.`} />}
      {!res && <div className="card p-6 text-muted">{run.status === "out" ? "Sensor still out on the course." : "Processing..."}</div>}
      {res && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            <Stat label="Time" value={fmtTime(res.elapsed_s)} sub={res.complete ? "complete" : "incomplete"} big />
            <Stat label="Stations" value={`${res.sequence?.order?.length ?? res.checkins.length}${cd ? " / " + cd.stations.filter((s: any) => s.required !== false).length : ""}`}
              sub={res.sequence?.missing_required?.length ? `missed ${res.sequence.missing_required.join(", ")}` : "all required found"} />
            <Stat label="Distance" value={fmtM(res.metrics.distance_m)} sub={run.summary?.extra_m != null ? `${fmtM(run.summary.extra_m)} more than the crew` : SOURCE_LABEL[res.positioning_mode === "gps" ? "gps" : res.positioning_mode === "fused" ? "fused" : "reconstructed"]} />
            <Stat label="Steps" value={fmtNum(res.metrics.steps)} sub={`${fmtNum(res.metrics.cadence_spm)} steps/min`} />
            <Stat label="vs crew par" value={fmtDelta(run.summary?.vs_par_s)} sub={run.summary?.par_s ? `par ${fmtTime(run.summary.par_s)}` : "no course"} />
            <Stat label="Steadiness" value={res.metrics.vibration_rms_g != null ? `${(res.metrics.vibration_rms_g * 1000).toFixed(1)} mg` : "--"} sub="vibration while walking" />
            <Stat label="Biggest bump" value={res.metrics.peak_g != null ? `${res.metrics.peak_g.toFixed(1)} g` : "--"} sub={res.metrics.peak_g_t != null ? `at ${fmtTime(res.metrics.peak_g_t - (res.start?.end ?? 0), 0)} (not ranked)` : ""} />
          </div>

          <div className="grid xl:grid-cols-[3fr_2fr] gap-6">
            <div className="card p-4">
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <h2 className="text-xl font-bold">Route replay <span className="text-muted text-base font-normal">({MODE_LABEL[res.positioning_mode] || res.positioning_mode})</span></h2>
                <div className="flex gap-2 items-center">
                  <span className="label">Ghost race</span>
                  <select className="input w-40" value={ghostVs} onChange={(e) => setGhostVs(e.target.value as any)}>
                    <option value="">none</option><option value="leader">current leader</option><option value="crew">crew survey</option>
                  </select>
                </div>
              </div>
              <ReplayBlock res={res} cd={cd} courseId={run.course_id} ghost={ghostVs ? ghost.data : null} />
              <div className="mt-3"><RouteLegend /></div>
              {res.route_notes?.fallback && <div className="text-warn text-sm mt-2">{res.route_notes.fallback}</div>}
            </div>
            <div className="card p-4">
              <h2 className="text-xl font-bold mb-2">Splits</h2>
              <table className="grid-table tabular">
                <thead><tr><th>Leg</th><th>Leg time</th><th>Split</th><th>Walked</th><th>Crew</th><th>Extra</th></tr></thead>
                <tbody>
                  {res.legs.map((l: any, i: number) => (
                    <tr key={i}>
                      <td className="whitespace-nowrap">{l.from_name} to {l.to_name}</td>
                      <td>{fmtTime(l.leg_time_s)}</td>
                      <td>{fmtTime(l.split_s)}</td>
                      <td>{fmtM(l.distance_m)}</td>
                      <td className="text-muted">{l.reference_m != null ? fmtM(l.reference_m) : "--"}{l.reference_kind === "estimated" ? "*" : ""}</td>
                      <td style={{ color: (l.extra_m ?? 0) > 15 ? "var(--warn)" : undefined }}>{l.extra_m != null ? fmtM(l.extra_m) : "--"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="text-xs text-muted mt-2">* crew distance estimated from straight line times the course detour factor (leg not walked in the survey)</div>
            </div>
          </div>

          <CheckinReview runId={+id} res={res} cd={cd} overrides={data.overrides} onSaved={reload} />
          <SensorView res={res} />
          {data.audit?.length > 0 && (
            <div className="card p-4">
              <h2 className="text-xl font-bold mb-2">Audit log</h2>
              {data.audit.map((a: any) => <div key={a.id} className="text-sm"><span className="text-muted">{new Date(a.at * 1000).toLocaleString()}</span> {a.action}{a.note ? `: ${a.note}` : ""}</div>)}
            </div>
          )}
        </div>
      )}
    </Page>
  );
}

function ReplayBlock({ res, cd, courseId, ghost }: { res: any; cd: any; courseId?: number; ghost: any }) {
  const t0 = res.start?.end ?? res.route.t[0] ?? 0;
  const t1 = res.finish?.start ?? res.route.t[res.route.t.length - 1] ?? 0;
  const main = { ...res.route, t0, label: "", color: "#ffffff" };
  let g = null;
  if (ghost?.route) {
    const gt = ghost.route.t as number[];
    const gt0 = ghost.start?.end ?? gt[0];
    g = { ...ghost.route, t0: gt0, label: ghost.name, color: "#b48cff" };
  }
  const booth = cd?.booth ?? { x: 0, y: 0 };
  const strays = res.strays.filter((s: any) => s.x != null).map((s: any) => ({ x: s.x, y: s.y, label: "stray" }));
  return (
    <Replay main={main} ghost={g} duration={Math.max(t1 - t0, 1)}
      checkins={res.checkins.filter((c: any) => c.station).map((c: any) => ({ t: c.rest_start, station: c.station }))}
      courseMap={{ courseId, booth, stations: cd?.stations, strays, background: cd?.background,
        reference: cd?.route ? { x: cd.route.x, y: cd.route.y, source: cd.route.source, color: "#9fb0c2", opacity: 0.3 } : null }} />
  );
}

function explain(c: any, names: Record<string, string> = {}) {
  const parts = [`still for ${Number(c.duration).toFixed(0)} s`];
  for (const m of c.methods || []) {
    if (m.method === "gps" && m.available) parts.push(`GPS ${m.distance_m} m from ${names[m.nearest] || m.nearest}`);
    if (m.method === "orientation") parts.push(m.reserved ? "lying flat face up" : `holder angle ${m.angle_deg} deg off`);
    if (m.method === "taps" && m.count) parts.push(`${m.count} taps`);
    if (m.method === "beacon" && m.freq_hz) parts.push(`${m.freq_hz} Hz tone`);
  }
  return parts.join(", ");
}

function CheckinReview({ runId, res, cd, overrides, onSaved }: { runId: number; res: any; cd: any; overrides: any; onSaved: () => void }) {
  const stations: any[] = cd?.stations || [];
  const names: Record<string, string> = Object.fromEntries([["BOOTH", "the booth"], ...stations.map((s) => [s.id, s.name])]);
  const initial = useMemo(() => res.checkins.map((c: any) => ({ ...c })), [res]);
  const [rows, setRows] = useState<any[]>(initial);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => setRows(initial), [initial]);
  const dirty = JSON.stringify(rows.map((r) => [r.station, r.rest_start, r.rest_end])) !== JSON.stringify(initial.map((r: any) => [r.station, r.rest_start, r.rest_end]));

  const save = async (clear = false) => {
    setErr(null);
    try {
      await api(`/api/runs/${runId}/checkins`, { method: "PUT", json: {
        checkins: clear ? null : rows.map((r) => ({ station: r.station, rest_start: +r.rest_start, rest_end: +r.rest_end, rest_mid: (+r.rest_start + +r.rest_end) / 2,
          duration: +r.rest_end - +r.rest_start, source: r.source === "auto" && !r._edited ? "auto" : "manual", status: "matched", methods: r.methods || [],
          x: r.x, y: r.y, match_distance_m: r.match_distance_m })),
        note: note || (clear ? "restored automatic check-ins" : ""),
      } });
      setNote("");
      onSaved();
    } catch (e: any) { setErr(e.message); }
  };
  const t0 = res.start?.end ?? 0;
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <h2 className="text-xl font-bold">Check-ins {res.sequence?.duplicates?.length ? <span className="text-warn text-base">duplicates: {res.sequence.duplicates.join(", ")}</span> : null}</h2>
        {overrides && <button className="btn text-sm" onClick={() => save(true)}>Restore automatic detection</button>}
      </div>
      <table className="grid-table">
        <thead><tr><th>At</th><th>Rest window (s)</th><th>Station</th><th>Status</th><th>How the sensor saw it</th><th></th></tr></thead>
        <tbody>
          <tr className="text-muted"><td>0:00</td><td className="tabular">{res.start ? `${res.start.start.toFixed(1)} to ${res.start.end.toFixed(1)}` : "missing"}</td><td>START</td><td>{res.start ? "booth" : <span className="text-bad">not found</span>}</td><td>{res.notes?.filter((n: string) => n.includes("START")).join(" ")}</td><td /></tr>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="tabular">{fmtTime(r.rest_start - t0, 0)}</td>
              <td className="tabular">
                <input className="input w-20 inline-block py-1" value={r.rest_start} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, rest_start: e.target.value, _edited: true } : x))} />
                {" to "}
                <input className="input w-20 inline-block py-1" value={r.rest_end} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, rest_end: e.target.value, _edited: true } : x))} />
              </td>
              <td>
                <select className="input py-1" value={r.station ?? ""} onChange={(e) => setRows(rows.map((x, j) => j === i ? { ...x, station: e.target.value || null, _edited: true } : x))}>
                  <option value="">(none)</option>
                  {stations.map((s) => <option key={s.id} value={s.id}>{s.number}. {s.name}</option>)}
                </select>
              </td>
              <td><StatusPill status={r.status} />{r.source === "manual" && <span className="pill ml-1 text-muted">manual</span>}{r.duplicate && <span className="pill ml-1 text-warn">duplicate</span>}
                {r.reason && <div className="text-xs text-warn">{r.reason}</div>}</td>
              <td className="text-sm">{r.methods?.length ? explain(r, names) : r.source === "manual" ? "added by staff" : `still for ${Number(r.duration).toFixed(0)} s`}</td>
              <td><button className="btn btn-danger text-sm" onClick={() => setRows(rows.filter((_, j) => j !== i))}>Remove</button></td>
            </tr>
          ))}
          <tr className="text-muted"><td>{fmtTime(res.elapsed_s, 0)}</td><td className="tabular">{res.finish ? `${res.finish.start.toFixed(1)} to ${res.finish.end.toFixed(1)}` : "missing"}</td><td>FINISH</td><td>{res.finish ? "booth" : <span className="text-bad">not found</span>}</td><td>{res.notes?.filter((n: string) => n.includes("FINISH")).join(" ")}</td><td /></tr>
        </tbody>
      </table>
      {res.strays.length > 0 && (
        <div className="mt-4">
          <div className="label mb-1">Stray stops (rests that matched no station; not scored)</div>
          {res.strays.map((s: any, i: number) => (
            <div key={i} className="flex items-center gap-3 text-sm py-1 flex-wrap">
              <span className="tabular">{fmtTime(s.rest_start - t0, 0)}</span>
              <span className="text-muted">{s.reason || s.status}. {explain(s, names)}</span>
              <select className="input py-1 w-56" defaultValue="" onChange={(e) => {
                if (!e.target.value) return;
                setRows([...rows, { ...s, station: e.target.value, source: "manual", _edited: true, status: "matched" }].sort((a, b) => a.rest_start - b.rest_start));
              }}>
                <option value="">Assign to station...</option>
                {stations.map((st) => <option key={st.id} value={st.id}>{st.number}. {st.name}</option>)}
              </select>
            </div>
          ))}
        </div>
      )}
      {res.rejected_rests?.length > 0 && (
        <div className="text-sm text-muted mt-3">
          Ignored pauses: {res.rejected_rests.map((r: any) => `${fmtTime(r.start - t0, 0)} (${r.reason === "hand_held" ? `held in a hand, tremor ${(r.tremor_rms_g * 1000).toFixed(1)} mg` : "too short"})`).join("; ")}
        </div>
      )}
      <div className="flex gap-2 mt-4 items-center flex-wrap">
        <button className="btn" onClick={() => {
          const last = rows[rows.length - 1];
          const s = last ? +last.rest_end + 30 : t0 + 30;
          setRows([...rows, { station: stations[0]?.id ?? null, rest_start: s.toFixed(1), rest_end: (s + 10).toFixed(1), duration: 10, status: "matched", source: "manual", methods: [], _edited: true }]);
        }}>Add check-in</button>
        {dirty && <>
          <input className="input flex-1 min-w-[240px]" placeholder="Audit note (required), e.g. participant showed photo at Station 4" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn btn-primary" disabled={!note.trim()} onClick={() => save()}>Save and rescore</button>
          <button className="btn" onClick={() => setRows(initial)}>Discard</button>
        </>}
      </div>
      <ErrorBox error={err} />
    </div>
  );
}

function SensorView({ res }: { res: any }) {
  const sv = res.sensor_view;
  const t0 = res.start?.start ?? 0;
  const still = sv.stillness;
  const series = useMemo(() => {
    const out: { title: string; x: number[]; ys: (number | null)[][]; labels: string[]; y?: string; logY?: boolean }[] = [];
    out.push({ title: "Stillness (rolling std of |acceleration|; low = still)", x: still.t, ys: [still.std_g.map((v: number) => v * 1000), still.still.map((v: number) => v ? 0 : null)], labels: ["std (mg)", "rest detected"], y: "mg" });
    if (sv.accel_mag) out.push({ title: "Acceleration magnitude", x: sv.accel_mag.t, ys: [sv.accel_mag.min, sv.accel_mag.max], labels: ["min (g)", "max (g)"], y: "g" });
    if (sv.gps) out.push({ title: "GPS fix quality (estimated error; gaps = no fix)", x: sv.gps.t, ys: [sv.gps.sigma_m.map((v: number, i: number) => sv.gps.ok[i] ? v : null)], labels: ["error (m)"], y: "m" });
    if (sv.env?.pressure) out.push({ title: "Pressure (stairs and floor changes)", x: sv.env.t, ys: [sv.env.pressure], labels: ["Pa"], y: "Pa" });
    if (sv.env?.temperature) out.push({ title: "Temperature", x: sv.env.t, ys: [sv.env.temperature], labels: ["°C"], y: "°C" });
    if (sv.light) out.push({ title: "Light", x: sv.light.t, ys: [sv.light.lux], labels: ["lux"], y: "lux" });
    return out;
  }, [sv, still]);
  return (
    <div className="card p-4">
      <h2 className="text-xl font-bold mb-1">How the sensor saw it</h2>
      <div className="text-muted text-sm mb-3">Every number above comes from these traces. Times are from the start of the recording ({fmtTime(t0, 0)} is the START rest).</div>
      <div className="grid xl:grid-cols-2 gap-4">
        {series.map((s) => (
          <div key={s.title}>
            <div className="label mb-1">{s.title}</div>
            <UPlotChart x={s.x} ys={s.ys} series={s.labels.map((l, i) => ({ label: l, color: i === 1 && s.title.startsWith("Stillness") ? "#3ddc84" : undefined, width: i === 1 && s.title.startsWith("Stillness") ? 6 : 1.5 }))}
              syncKey="sensorview" height={180} xTime yLabel={s.y} />
          </div>
        ))}
      </div>
    </div>
  );
}
