"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import CourseMap from "./CourseMap";
import Heatmap from "./Heatmap";
import ReplayScene from "./ReplayScene";
import UPlotChart from "./UPlotChart";
import { useApi } from "@/lib/api";
import { fmtTime } from "@/lib/format";

/* The display's Recording Explorer panel: walks through one recording the way a
   visitor would in Recording Explorer (replay, shock, spectrum, environment,
   route, and the story last), then hands back to the rotation with onDone. */

const REPLAY_SECONDS = 45;          // the whole recording replays in about this long

export default function ExplorerMarquee({ rec, secs, onDone }: { rec: any; secs: number; onDone: () => void }) {
  const a = useApi<any>(`/api/recordings/${rec.id}/analysis`);
  const f = useApi<any>(`/api/recordings/${rec.id}/analysis?part=frequency`);
  const r = useApi<any>(`/api/recordings/${rec.id}/replay`);
  const done = useRef(onDone);
  done.current = onDone;

  // start once every part has loaded (or failed), so the list of screens does not shift
  const settled = !!a.data && (!!r.data || !!r.error) && (!!f.data || !!f.error);
  const screens = useMemo(() => {
    const d = a.data;
    if (!d || !settled) return [];
    const out: string[] = [];
    // playback first, then the dashboards, then the story to finish
    if (r.data) out.push("replay");
    if (d.shock?.available) out.push("shock");
    if (f.data?.available && f.data.spectrogram) out.push("frequency");
    if (d.environment?.available && (d.environment.altitude_m || d.environment.temperature)) out.push("environment");
    if (d.gps?.available || d.track?.available) out.push("route");
    if (d.story?.timeline?.length) out.push("story");
    return out;
  }, [a.data, f.data, r.data, settled]);

  const [k, setK] = useState(0);
  const cur = screens[k];
  const next = () => setK((v) => v + 1);
  useEffect(() => { if (settled && k >= screens.length) done.current(); }, [k, screens.length, settled]);
  useEffect(() => {
    if (a.error) { const t = setTimeout(() => done.current(), 2000); return () => clearTimeout(t); }
  }, [a.error]);
  useEffect(() => {
    if (!cur) return;
    // the replay ends by itself; the time limit is only a safety net
    const t = setTimeout(next, cur === "replay" ? (REPLAY_SECONDS + 30) * 1000 : secs * 1000);
    return () => clearTimeout(t);
  }, [cur, k, secs]);

  if (!a.data || !cur) return <div className="h-full grid place-items-center text-3xl text-muted">Loading {rec.title}...</div>;
  const d = a.data;
  const label: Record<string, string> = { replay: "Reconstructed replay", story: "What happened", shock: "Shock and events",
    frequency: "Vibration spectrum", environment: "Environment", route: "Route" };
  return (
    <div className="h-full flex flex-col gap-4">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-2xl text-accent uppercase tracking-widest font-bold">Recording Explorer · {label[cur]}</div>
          <h2 className="text-5xl font-extrabold">{rec.title}</h2>
        </div>
        <div className="flex gap-2 pb-2">{screens.map((s, i) => <span key={s} className={`w-3 h-3 rounded-full ${i === k ? "bg-accent" : "bg-line"}`} />)}</div>
      </div>
      <div className="flex-1 min-h-0">
        {cur === "replay" && <ReplayFit data={r.data} title={rec.title} onEnd={next} />}
        {cur === "story" && <StoryScreen st={d.story} />}
        {cur === "shock" && <ShockScreen s={d.shock} />}
        {cur === "frequency" && <FrequencyScreen f={f.data} />}
        {cur === "environment" && <EnvScreen e={d.environment} />}
        {cur === "route" && <RouteScreen d={d} />}
      </div>
    </div>
  );
}

function ReplayFit({ data, title, onEnd }: { data: any; title: string; onEnd: () => void }) {
  const speed = Math.max(1, Math.round(data.duration_s / REPLAY_SECONDS));
  return (
    <div className="h-full flex flex-col items-center">
      {/* the canvas is 16:9; keep it inside the panel height */}
      <div className="h-full aspect-video max-w-full"><ReplayScene data={data} title={title} kiosk={{ speed, onEnd }} /></div>
    </div>
  );
}

function StoryScreen({ st }: { st: any }) {
  return (
    <div className="grid grid-cols-[3fr_2fr] gap-8 h-full">
      <ol className="space-y-3 overflow-hidden">
        {st.timeline.slice(0, 7).map((h: any, i: number) => (
          <li key={i} className="flex gap-6 items-baseline">
            <span className="text-4xl font-black tabular text-brand w-28 text-right">{h.time}</span>
            <span><span className="text-4xl font-bold">{h.title}</span><div className="text-2xl text-muted">{h.detail}</div></span>
          </li>
        ))}
      </ol>
      <div className="space-y-4 overflow-hidden">
        {st.facts.slice(0, 5).map((h: any, i: number) => (
          <div key={i} className="card p-5"><div className="text-3xl font-bold">{h.title}</div><div className="text-xl text-muted">{h.detail}</div></div>
        ))}
      </div>
    </div>
  );
}

function Big({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="card p-6">
      <div className="text-xl text-muted uppercase tracking-wider">{label}</div>
      <div className="text-6xl font-black tabular mt-1">{value}</div>
      {sub && <div className="text-xl text-muted mt-1">{sub}</div>}
    </div>
  );
}

function ShockScreen({ s }: { s: any }) {
  const srs = s.srs?.[0];
  const axes = srs ? Object.keys(srs).filter((k) => !["f", "t"].includes(k)) : [];
  return (
    <div className="grid grid-cols-[2fr_3fr] gap-6 h-full">
      <div className="space-y-4">
        <Big label="Biggest hit" value={`${s.summary.peak_g?.toFixed(1)} g`} sub={`at ${fmtTime(s.summary.peak_t)}`} />
        <Big label="Vibration" value={`${s.summary.vibration_rms_g.toFixed(2)} g`} sub="RMS over the whole recording" />
        <div className="card p-5 space-y-1">
          {s.events.slice(1, 5).map((e: any, i: number) => (
            <div key={i} className="flex justify-between text-2xl tabular"><span className="text-muted">{fmtTime(e.t)}</span><b>{e.resultant_g.toFixed(1)} g</b></div>
          ))}
        </div>
      </div>
      {srs && (
        <div className="card p-5">
          <div className="text-xl text-muted mb-2">Shock response spectrum of the biggest hit</div>
          <UPlotChart x={srs.f} ys={axes.map((k) => srs[k])} series={axes.map((k) => ({ label: k }))} logX logY height={480} xLabel="Hz" yLabel="g" />
        </div>
      )}
    </div>
  );
}

function FrequencyScreen({ f }: { f: any }) {
  const top = (f.peaks || []).filter((p: any) => p.rank === 1);
  return (
    <div className="h-full flex flex-col gap-4">
      <div className="flex gap-3 flex-wrap text-2xl">
        {top.map((p: any, i: number) => <span key={i} className="pill text-2xl px-4 py-1">{p.axis}: strongest at {p.f_hz} Hz</span>)}
      </div>
      <div className="card p-5 flex-1">
        <div className="text-xl text-muted mb-2">Spectrogram: vibration frequency over time (brighter is stronger)</div>
        <Heatmap t={f.spectrogram.t} f={f.spectrogram.f} z={f.spectrogram.log10_psd} height={520} />
      </div>
    </div>
  );
}

function EnvScreen({ e }: { e: any }) {
  return (
    <div className="h-full flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-4">
        {e.altitude && <Big label="Highest point" value={`${e.altitude.max_m} m`} sub={`at ${fmtTime(e.altitude.max_t)}, from air pressure`} />}
        {e.ranges?.temperature && <Big label="Temperature" value={`${e.ranges.temperature[0]} to ${e.ranges.temperature[1]} °C`} />}
        {e.ranges?.humidity && <Big label="Humidity" value={`${e.ranges.humidity[0].toFixed(0)} to ${e.ranges.humidity[1].toFixed(0)} %`} />}
      </div>
      <div className="grid grid-cols-2 gap-4 flex-1">
        {e.altitude_m && <div className="card p-4"><div className="text-xl text-muted mb-1">Relative altitude (m)</div>
          <UPlotChart x={e.t} ys={[e.altitude_m]} series={[{ label: "altitude m" }]} height={380} xTime /></div>}
        {e.temperature && <div className="card p-4"><div className="text-xl text-muted mb-1">Temperature (°C)</div>
          <UPlotChart x={e.t} ys={[e.temperature]} series={[{ label: "°C" }]} height={380} xTime /></div>}
      </div>
    </div>
  );
}

function RouteScreen({ d }: { d: any }) {
  const g = d.gps, t = d.track;
  if (g?.available) return <CourseMap routes={[{ x: g.x, y: g.y, source: "gps" }]} height={640} />;
  const c = t.course;
  const n = t.x.length - 1;
  return (
    <div className="h-full">
      <CourseMap courseId={c?.id} booth={c?.booth ?? null} stations={c?.stations} background={c?.background}
        markers={c ? undefined : [{ x: t.x[0], y: t.y[0], color: "var(--good)", label: "Start" }, { x: t.x[n], y: t.y[n], color: "var(--accent)", label: "End" }]}
        routes={[{ x: t.x, y: t.y, source: t.route_source || "reconstructed" }]} highlight={t.visited} height={640} />
      <div className="text-2xl text-muted mt-2">{t.distance_m} m, reconstructed from steps and heading.</div>
    </div>
  );
}
