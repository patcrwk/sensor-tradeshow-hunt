"use client";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import CourseMap from "@/components/CourseMap";
import Heatmap from "@/components/Heatmap";
import ReplayScene from "@/components/ReplayScene";
import { ErrorBox, Page, Stat, StatusPill, Tabs } from "@/components/Nav";
import UPlotChart, { PALETTE } from "@/components/UPlotChart";
import { api, useApi } from "@/lib/api";
import { fmtTime } from "@/lib/format";

const TAB_LABEL: Record<string, string> = {
  overview: "Overview", timeseries: "Time Series", frequency: "Frequency", shock: "Shock and Events",
  environment: "Environment", motion: "Motion and Location", story: "Story", replay: "Replay",
};

export default function RecordingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const rec = useApi<any>(`/api/recordings/${id}`, ["recording"]);
  const ready = rec.data?.status === "ready";
  const a = useApi<any>(ready ? `/api/recordings/${id}/analysis` : null, ["recording"]);
  const tabs: string[] = a.data?.profile?.tabs || Object.keys(TAB_LABEL);
  const [tab, setTab] = useState<string>("");
  const cur = tab || tabs[0];

  if (rec.error) return <Page title="Recording"><ErrorBox error={rec.error} /></Page>;
  if (!rec.data) return <Page title="Recording">Loading...</Page>;
  return (
    <Page wide title={rec.data.title} actions={<><StatusPill status={rec.data.status} /><ProfilePicker rec={rec.data} onChange={() => { rec.reload(); a.reload(); }} /></>}>
      {rec.data.status === "processing" && <div className="card p-6 text-muted">Analyzing once; tabs load instantly after this...</div>}
      {rec.data.status === "error" && <ErrorBox error={rec.data.error} />}
      {a.data && (
        <>
          {a.data.overview.notes.map((n: string, i: number) => <div key={i} className="text-warn text-sm mb-1">{n}</div>)}
          <Tabs value={cur} onChange={setTab} tabs={tabs.map((t) => ({ id: t, label: TAB_LABEL[t] }))} />
          {cur === "overview" && <Overview o={a.data.overview} rec={rec.data} />}
          {cur === "timeseries" && <TimeSeries id={id} o={a.data.overview} featured={a.data.profile.featured_roles} />}
          {cur === "frequency" && <Frequency id={id} />}
          {cur === "shock" && <Shock s={a.data.shock} />}
          {cur === "environment" && <Environment e={a.data.environment} />}
          {cur === "motion" && <Motion m={a.data.motion} g={a.data.gps} />}
          {cur === "replay" && <ReplayTab id={id} title={rec.data.title} />}
          {cur === "story" && <Story rec={rec.data} st={a.data.story} onSaved={() => { rec.reload(); a.reload(); }} />}
        </>
      )}
    </Page>
  );
}

function ProfilePicker({ rec, onChange }: { rec: any; onChange: () => void }) {
  const profiles = useApi<any[]>("/api/profiles");
  return (
    <div className="flex gap-2 items-center">
      <select className="input w-44" value={rec.profile} onChange={async (e) => { await api(`/api/recordings/${rec.id}`, { method: "PATCH", json: { profile: e.target.value } }); onChange(); }}>
        {profiles.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <label className="flex gap-1 items-center text-sm"><input type="checkbox" checked={rec.in_library}
        onChange={async (e) => { await api(`/api/recordings/${rec.id}`, { method: "PATCH", json: { in_library: e.target.checked } }); onChange(); }} /> in library</label>
    </div>
  );
}

function ReplayTab({ id, title }: { id: string; title: string }) {
  const { data, error } = useApi<any>(`/api/recordings/${id}/replay`);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <div className="card p-6 text-muted">Reconstructing the recording from the sensor data (first time only)...</div>;
  return <div className="card p-4"><ReplayScene data={data} title={title} /></div>;
}

function Overview({ o, rec }: { o: any; rec: any }) {
  const d = o.device;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <Stat label="Device" value={d.model || "--"} sub={d.recorder_name} />
        <Stat label="Serial" value={d.serial ?? "--"} sub={`firmware ${d.firmware ?? "--"}`} />
        <Stat label="Started" value={o.start_utc ? new Date(o.start_utc).toLocaleDateString() : "--"} sub={o.start_utc ? new Date(o.start_utc).toUTCString().slice(17, 25) + " UTC" : ""} />
        <Stat label="Duration" value={fmtTime(o.duration_s, 0)} sub={`${o.duration_s?.toFixed(1)} s`} />
        <Stat label="File size" value={o.file.size ? `${(o.file.size / 1e6).toFixed(1)} MB` : "--"} sub={o.file.file} />
        <Stat label="Calibration" value={d.calibration_expired ? "Expired" : d.calibration_expiry ? "Valid" : "--"} sub={d.calibration_expiry ? `expiry ${d.calibration_expiry}` : ""} />
      </div>
      {rec.description && <div className="card p-4">{rec.description}</div>}
      <div className="card p-4">
        <h2 className="text-xl font-bold mb-2">Channels</h2>
        <table className="grid-table">
          <thead><tr><th>ID</th><th>Name</th><th>Rate</th><th>Samples</th><th>Subchannels</th><th>Role</th></tr></thead>
          <tbody>
            {o.channels.map((c: any) => (
              <tr key={c.id}>
                <td className="tabular">{c.id}</td><td className="font-semibold">{c.name}</td>
                <td className="tabular">{c.rate_hz >= 100 ? c.rate_hz.toFixed(0) : c.rate_hz.toFixed(1)} Hz</td>
                <td className="tabular">{c.samples?.toLocaleString()}</td>
                <td className="text-sm">{c.subchannels.map((s: any) => `${s.name} (${s.units})`).join(", ")}</td>
                <td className="text-sm text-muted">{Object.entries(o.roles).filter(([, v]) => v === c.id || (Array.isArray(v) && (v as any[]).includes(c.id))).map(([k]) => k).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="text-sm text-muted mt-2">Location channel: {o.roles.gps ? `found (${o.gps_fields.join(", ")})` : "none in this recording"}</div>
      </div>
    </div>
  );
}

function TimeSeries({ id, o, featured }: { id: string; o: any; featured: string[] }) {
  const chans = useMemo(() => {
    const ids: any[] = [];
    for (const r of featured) { const v = o.roles[r]; if (v != null && !Array.isArray(v) && !ids.includes(v)) ids.push(v); }
    for (const c of o.channels) if (!ids.includes(c.id)) ids.push(c.id);
    if (o.roles.gps) ids.push("gps");
    return ids;
  }, [o, featured]);
  const [range, setRange] = useState<[number, number] | null>(null);
  return (
    <div className="space-y-4">
      <div className="flex gap-3 items-center">
        <span className="text-muted text-sm">Drag across any plot to zoom all of them. Data is re-fetched at the zoomed resolution (min/max per pixel, so peaks are never lost).</span>
        {range && <button className="btn text-sm" onClick={() => setRange(null)}>Reset zoom</button>}
        {range && <span className="text-sm tabular">{fmtTime(range[0])} to {fmtTime(range[1])}</span>}
      </div>
      {chans.map((c) => <ChannelPlot key={c} id={id} ch={c} info={o.channels.find((x: any) => x.id === c)} range={range} setRange={setRange} />)}
    </div>
  );
}

function ChannelPlot({ id, ch, info, range, setRange }: { id: string; ch: any; info: any; range: [number, number] | null; setRange: (r: [number, number]) => void }) {
  const [d, setD] = useState<any>(null);
  const load = useCallback(async () => {
    const q = range ? `&t0=${range[0]}&t1=${range[1]}` : "";
    setD(await api(`/api/recordings/${id}/timeseries?ch=${ch}&n=1200${q}`));
  }, [id, ch, range]);
  useEffect(() => { load(); }, [load]);
  const cols = d ? Object.keys(d.series) : [];
  const ys = useMemo(() => cols.flatMap((c) => d.decimated ? [d.series[c].min, d.series[c].max] : [d.series[c].max]), [d]);
  if (!d) return <div className="card p-4 text-muted">Loading {info?.name ?? ch}...</div>;
  const units = info?.subchannels?.[0]?.units || "";
  return (
    <div className="card p-3">
      <div className="label mb-1">{info?.name ?? "GPS"} {d.decimated && <span className="normal-case text-muted">(min/max of {d.n_raw.toLocaleString()} samples)</span>}</div>
      <UPlotChart x={d.t} ys={ys} height={170} syncKey="ts" xTime yLabel={units} xRange={range}
        series={cols.flatMap((c, i) => d.decimated
          ? [{ label: `${c} min`, color: PALETTE[i], width: 1 }, { label: `${c} max`, color: PALETTE[i], width: 1 }]
          : [{ label: c, color: PALETTE[i] }])}
        onZoom={(a, b) => setRange([a, b])} />
    </div>
  );
}

function Frequency({ id }: { id: string }) {
  const { data: f } = useApi<any>(`/api/recordings/${id}/analysis?part=frequency`);
  const [oct, setOct] = useState(false);
  if (!f) return <div className="text-muted">Loading...</div>;
  if (!f.available) return <div className="text-muted">No accelerometer channel.</div>;
  const axes = Object.keys(f.psd).filter((k) => k !== "f");
  const top = f.peaks.filter((p: any) => p.rank <= 2);
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="flex justify-between items-center mb-1">
          <div className="label">{oct ? "Third-octave bands" : "Power spectral density"} · {f.channel_name} · {f.units}</div>
          <button className="btn text-sm" onClick={() => setOct(!oct)}>{oct ? "Show PSD" : "Show octave bands"}</button>
        </div>
        {oct
          ? <UPlotChart x={f.octave.f} ys={Object.keys(f.octave).filter((k) => k !== "f").map((k) => f.octave[k])} series={Object.keys(f.octave).filter((k) => k !== "f").map((k) => ({ label: k }))} logX logY height={320} xLabel="Hz" />
          : <UPlotChart x={f.psd.f.map((v: number) => Math.max(v, 0.5))} ys={axes.map((k) => f.psd[k].map((v: number) => Math.max(v, 1e-12)))} series={axes.map((k) => ({ label: k }))} logX logY height={320} xLabel="Hz" />}
        <div className="text-xs text-muted mt-1">{f.source.method}</div>
      </div>
      <div className="card p-4">
        <div className="label mb-2">Dominant peaks</div>
        <div className="flex gap-3 flex-wrap">
          {top.map((p: any, i: number) => <span key={i} className="pill text-base">{p.axis}: {p.f_hz} Hz{p.rank === 1 ? " (strongest)" : ""}</span>)}
        </div>
      </div>
      <div className="card p-4">
        <div className="label mb-2">Spectrogram (resultant, log power)</div>
        <Heatmap t={f.spectrogram.t} f={f.spectrogram.f} z={f.spectrogram.log10_psd} height={300} />
      </div>
    </div>
  );
}

function Shock({ s }: { s: any }) {
  const [sel, setSel] = useState(0);
  if (!s.available) return <div className="text-muted">No accelerometer channel.</div>;
  const srs = s.srs[Math.min(sel, s.srs.length - 1)];
  const axes = srs ? Object.keys(srs).filter((k) => !["f", "t"].includes(k)) : [];
  return (
    <div className="grid xl:grid-cols-2 gap-4">
      <div className="card p-4">
        <div className="grid grid-cols-3 gap-3 mb-4">
          <Stat label="Peak" value={`${s.summary.peak_g?.toFixed(1)} g`} sub={`at ${fmtTime(s.summary.peak_t)}`} />
          <Stat label="Vibration RMS" value={`${s.summary.vibration_rms_g.toFixed(3)} g`} sub="whole recording" />
          <Stat label="Events" value={s.events.length} sub={s.channel_name} />
        </div>
        <table className="grid-table tabular">
          <thead><tr><th>#</th><th>Time</th><th>Resultant</th><th>X</th><th>Y</th><th>Z</th></tr></thead>
          <tbody>
            {s.events.map((e: any, i: number) => (
              <tr key={i} className={i < s.srs.length ? "cursor-pointer hover:bg-panel-2" : ""} onClick={() => i < s.srs.length && setSel(i)}
                style={{ background: sel === i ? "var(--panel-2)" : undefined }}>
                <td>{i + 1}</td><td>{fmtTime(e.t)}</td><td className="font-bold">{e.resultant_g.toFixed(2)} g</td>
                <td>{e.x_g.toFixed(2)}</td><td>{e.y_g.toFixed(2)}</td><td>{e.z_g.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="text-xs text-muted mt-2">{s.source.method}. Click one of the top three events to see its shock response spectrum.</div>
      </div>
      <div className="card p-4">
        {srs && <>
          <div className="label mb-1">Shock response spectrum, event at {fmtTime(srs.t)} (5% damping)</div>
          <UPlotChart x={srs.f} ys={axes.map((k) => srs[k])} series={axes.map((k) => ({ label: k }))} logX logY height={320} xLabel="Hz" yLabel="g" />
        </>}
        {s.metrics?.rows && <details className="mt-4"><summary className="cursor-pointer label">Shock and vibration metrics (endaq.calc.stats.shock_vibe_metrics, 2 s around the peak)</summary>
          <table className="grid-table text-xs mt-2"><thead><tr>{s.metrics.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
            <tbody>{s.metrics.rows.slice(0, 60).map((r: any[], i: number) => <tr key={i}>{r.map((v, j) => <td key={j}>{String(v)}</td>)}</tr>)}</tbody></table>
        </details>}
      </div>
    </div>
  );
}

function Environment({ e }: { e: any }) {
  if (!e.available) return <div className="text-muted">No environmental channels.</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {e.altitude && <Stat label="Max relative altitude" value={`${e.altitude.max_m} m`} sub={`at ${fmtTime(e.altitude.max_t)} from ${e.altitude.pressure_drop_pa} Pa`} />}
        {e.ranges?.temperature && <Stat label="Temperature" value={`${e.ranges.temperature[0]} to ${e.ranges.temperature[1]} °C`} />}
        {e.ranges?.humidity && <Stat label="Humidity" value={`${e.ranges.humidity[0].toFixed(0)} to ${e.ranges.humidity[1].toFixed(0)} %`} />}
        {e.light && <Stat label="Light (max)" value={`${e.light.max_lux} lux`} sub={e.light.max_lux <= 0.5 ? "sensor enclosed" : ""} />}
      </div>
      <div className="grid xl:grid-cols-2 gap-4">
        {e.altitude_m && <Chart title="Relative altitude from pressure (m)" x={e.t} ys={[e.altitude_m]} labels={["altitude m"]} />}
        {e.pressure && <Chart title="Pressure (Pa)" x={e.t} ys={[e.pressure, ...(e.secondary?.pressure ? [] : [])]} labels={["internal"]} />}
        {e.temperature && <Chart title="Temperature (°C)" x={e.t} ys={[e.temperature]} labels={["internal"]} x2={e.secondary?.t} y2={e.secondary?.temperature} />}
        {e.humidity && <Chart title="Relative humidity (%)" x={e.t} ys={[e.humidity]} labels={["internal"]} />}
        {e.light && <Chart title="Light (lux)" x={e.light.t} ys={[e.light.lux]} labels={["lux"]} />}
      </div>
      <div className="text-xs text-muted">{e.altitude?.source?.method}</div>
    </div>
  );
}

function Chart({ title, x, ys, labels, x2, y2 }: { title: string; x: number[]; ys: number[][]; labels: string[]; x2?: number[]; y2?: number[] }) {
  return (
    <div className="card p-3">
      <div className="label mb-1">{title}{x2 && y2 ? " (secondary sensor shown in the Time Series tab)" : ""}</div>
      <UPlotChart x={x} ys={ys} series={labels.map((l) => ({ label: l }))} height={200} syncKey="env" xTime />
    </div>
  );
}

function Motion({ m, g }: { m: any; g: any }) {
  const [colorBy, setColorBy] = useState<string>("");
  return (
    <div className="space-y-4">
      {m.available && <>
        <div className="grid grid-cols-3 gap-3">
          {Object.entries(m.peaks_dps).map(([k, v]: any) => <Stat key={k} label={`Peak rotation ${k}`} value={`${v} deg/s`} />)}
        </div>
        <div className="grid xl:grid-cols-2 gap-4">
          <div className="card p-3"><div className="label mb-1">Rotation rate (deg/s)</div>
            <UPlotChart x={m.t} ys={["x", "y", "z"].map((k) => m.rate[k])} series={["x", "y", "z"].map((k) => ({ label: k }))} height={220} syncKey="mo" xTime /></div>
          <div className="card p-3"><div className="label mb-1">Integrated attitude (deg, drifts; shows shape)</div>
            <UPlotChart x={m.t} ys={["x", "y", "z"].map((k) => m.integrated_deg[k])} series={["x", "y", "z"].map((k) => ({ label: k }))} height={220} syncKey="mo" xTime /></div>
          {m.tilt && <div className="card p-3"><div className="label mb-1">Tilt from gravity (deg)</div>
            <UPlotChart x={m.tilt.t} ys={[m.tilt.roll_deg, m.tilt.pitch_deg]} series={[{ label: "roll" }, { label: "pitch" }]} height={220} syncKey="mo" xTime /></div>}
        </div>
      </>}
      <div className="card p-4">
        <div className="flex justify-between items-center mb-2">
          <div className="label">GPS track</div>
          {g.available && <select className="input w-56" value={colorBy} onChange={(e) => setColorBy(e.target.value)}>
            <option value="">color: none</option>{Object.keys(g.colors).map((k) => <option key={k} value={k}>color: {k}</option>)}</select>}
        </div>
        {g.available ? <GpsTrack g={g} colorBy={colorBy} /> : <div className="text-muted">{g.reason || "No location channel"}. Recordings from GPS-equipped sensors show their track here.</div>}
      </div>
    </div>
  );
}

function GpsTrack({ g, colorBy }: { g: any; colorBy: string }) {
  const vals: number[] | undefined = colorBy ? g.colors[colorBy] : undefined;
  const lo = vals ? Math.min(...vals) : 0, hi = vals ? Math.max(...vals) : 1;
  const segs = useMemo(() => {
    if (!vals) return [{ x: g.x, y: g.y, source: "gps" as const }];
    // Contiguous runs of the same color bin become one polyline each
    const n = 16, out: any[] = [];
    let cur: any = null;
    for (let i = 1; i < g.x.length; i++) {
      const b = Math.min(n - 1, Math.floor(((vals[i] - lo) / (hi - lo || 1)) * n));
      if (!cur || cur.b !== b) {
        cur = { b, x: [g.x[i - 1]], y: [g.y[i - 1]], color: `hsl(${240 - (240 * (b + 0.5)) / n},90%,55%)` };
        out.push(cur);
      }
      cur.x.push(g.x[i]); cur.y.push(g.y[i]);
    }
    return out;
  }, [g, vals, lo, hi]);
  return (
    <>
      <CourseMap routes={segs as any} height={600} />
      <div className="text-sm text-muted mt-1">{g.distance_m} m, fix {Math.round(g.fix_ratio * 100)}% of the time{vals ? `; ${colorBy} ${lo.toFixed(2)} (blue) to ${hi.toFixed(2)} (red)` : ""}</div>
    </>
  );
}

function Story({ rec, st, onSaved }: { rec: any; st: any; onSaved: () => void }) {
  const [anns, setAnns] = useState<any[]>(rec.annotations || []);
  const [t, setT] = useState("");
  const [title, setTitle] = useState("");
  const [detail, setDetail] = useState("");
  const save = async (next: any[]) => { setAnns(next); await api(`/api/recordings/${rec.id}`, { method: "PATCH", json: { annotations: next } }); onSaved(); };
  return (
    <div className="grid xl:grid-cols-[3fr_2fr] gap-6">
      <div className="card p-6">
        <div className="text-accent uppercase tracking-widest font-bold">What the sensor recorded</div>
        <h2 className="text-4xl font-extrabold mb-6">{rec.title}</h2>
        <ol className="space-y-4">
          {st.timeline.map((h: any, i: number) => (
            <li key={i} className="flex gap-5 items-baseline">
              <span className="text-3xl font-black tabular text-brand w-24 text-right shrink-0">{h.time}</span>
              <div><div className="text-2xl font-bold">{h.title} {h.kind === "curated" && <span className="pill text-xs text-muted">curated</span>}</div>
                <div className="text-muted">{h.detail}</div>
                {h.source?.method && <div className="text-xs text-muted mt-1">source: {h.source.channel ? `${h.source.channel}, ` : ""}{h.source.method}</div>}</div>
            </li>
          ))}
        </ol>
      </div>
      <div className="space-y-3">
        {st.facts.map((h: any, i: number) => (
          <div key={i} className="card p-4"><div className="text-xl font-bold">{h.title}</div><div className="text-muted">{h.detail}</div>
            {h.source?.method && <div className="text-xs text-muted mt-1">source: {h.source.method}</div>}</div>
        ))}
        <div className="card p-4 space-y-2">
          <div className="label">Curated annotations</div>
          {anns.map((a, i) => <div key={i} className="flex justify-between text-sm"><span>{a.t != null ? fmtTime(a.t, 0) + " " : ""}{a.title}</span>
            <button className="text-bad" onClick={() => save(anns.filter((_, j) => j !== i))}>remove</button></div>)}
          <div className="grid grid-cols-[80px_1fr] gap-2">
            <input className="input" placeholder="sec" value={t} onChange={(e) => setT(e.target.value)} />
            <input className="input" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <input className="input" placeholder="Detail" value={detail} onChange={(e) => setDetail(e.target.value)} />
          <button className="btn" disabled={!title} onClick={() => { save([...anns, { t: t === "" ? null : +t, title, detail }]); setT(""); setTitle(""); setDetail(""); }}>Add annotation</button>
        </div>
      </div>
    </div>
  );
}
