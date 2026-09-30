"use client";
import { useEffect, useMemo, useState } from "react";
import CourseMap from "@/components/CourseMap";
import Leaderboard from "@/components/Leaderboard";
import { useSettings } from "@/components/BrandProvider";
import { turbo } from "@/components/Heatmap";
import { api, useApi, useEvents } from "@/lib/api";
import { fmtM, fmtNum, fmtTime } from "@/lib/format";

export default function Display() {
  const { settings } = useSettings();
  const kiosk = settings?.kiosk;
  const lbs = useApi<Record<string, any>>("/api/leaderboards?limit=8", ["leaderboard", "reset"], 60000);
  const dash = useApi<any>("/api/dashboard", ["leaderboard", "reset"], 60000);
  const course = useApi<any>("/api/courses/active", ["course", "reset"]);
  const library = useApi<any[]>("/api/recordings?library=true", ["recording"]);
  const [i, setI] = useState(0);
  const [flash, setFlash] = useState<any | null>(null);
  const [storyIdx, setStoryIdx] = useState(0);

  const panels = useMemo(() => {
    const p = kiosk?.panels?.length ? kiosk.panels : ["leaderboard:fastest", "crowd"];
    return p.filter((x) => !(x === "story:library" && !library.data?.some((r) => r.status === "ready")));
  }, [kiosk, library.data]);
  const secs = kiosk?.seconds_per_panel || 15;

  useEffect(() => {
    const t = setInterval(() => {
      setI((v) => (v + 1) % Math.max(panels.length, 1));
      setStoryIdx((v) => v + 1);
    }, secs * 1000);
    return () => clearInterval(t);
  }, [panels.length, secs]);

  // A new finisher interrupts the rotation
  useEvents(async (m) => {
    if (m.kind === "run" && m.status === "published") {
      try {
        const r = await api(`/api/runs/${m.run_id}`);
        const lb = await api(`/api/leaderboard?category=fastest&limit=100`);
        const rank = lb.rows.find((x: any) => x.run_id === m.run_id)?.rank;
        setFlash({ ...r.run, rank });
        setTimeout(() => setFlash(null), 12000);
      } catch {}
    }
  });

  const cur = panels[i % Math.max(panels.length, 1)] || "leaderboard:fastest";
  const b = settings?.branding;
  const stories = (library.data || []).filter((r) => r.status === "ready" && (!kiosk?.story_recording_ids?.length || kiosk.story_recording_ids.includes(r.id)));
  const story = stories.length ? stories[storyIdx % stories.length] : null;

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-bg cursor-none">
      <header className="flex items-center justify-between px-12 py-6 border-b border-line">
        <div className="flex items-center gap-6">
          {b?.logo_url ? <img src={b.logo_url} className="h-16" alt="" /> : <span className="text-5xl font-black text-brand">{b?.company || "enDAQ"}</span>}
          <span className="text-4xl font-bold">{b?.event_name}</span>
        </div>
        <Clock />
      </header>
      <main className="flex-1 px-12 py-8 overflow-hidden">
        {flash ? <Flash run={flash} /> :
          cur.startsWith("leaderboard:") ? <Leaderboard id={cur.split(":")[1]} lb={lbs.data?.[cur.split(":")[1]]} big limit={8} /> :
          cur === "crowd" ? <Crowd d={dash.data} /> :
          cur === "heatmap" ? <HeatPanel d={dash.data} course={course.data} /> :
          cur === "environment" ? <EnvPanel d={dash.data} course={course.data} /> :
          cur === "course" ? <CoursePanel course={course.data} /> :
          cur === "story:library" && story ? <StoryPanel rec={story} /> :
          <Leaderboard id="fastest" lb={lbs.data?.fastest} big limit={8} />}
      </main>
      <footer className="px-12 py-4 flex items-center justify-between border-t border-line">
        <div className="text-2xl text-muted">{b?.tagline}</div>
        <div className="flex gap-2">{panels.map((_, k) => <span key={k} className={`w-3 h-3 rounded-full ${k === i % panels.length ? "bg-brand" : "bg-line"}`} />)}</div>
      </footer>
    </div>
  );
}

function Clock() {
  const [t, setT] = useState<string>("");
  useEffect(() => {
    const f = () => setT(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    f();
    const id = setInterval(f, 10000);
    return () => clearInterval(id);
  }, []);
  return <span className="text-4xl font-bold tabular text-muted">{t}</span>;
}

function Flash({ run }: { run: any }) {
  const s = run.summary || {};
  return (
    <div className="h-full flex flex-col items-center justify-center text-center gap-6">
      <div className="text-4xl text-accent font-bold uppercase tracking-widest">New finisher</div>
      <div className="text-9xl font-black">{run.name}</div>
      <div className="text-8xl font-black tabular text-brand">{fmtTime(run.elapsed_s)}</div>
      <div className="text-4xl text-muted">
        {run.rank ? `#${run.rank} on the leaderboard · ` : ""}{s.stations ?? 0} stations · {fmtNum(s.steps)} steps · {fmtM(s.distance_m)}
      </div>
      {!run.complete && <div className="text-3xl text-warn">Missed {s.missing?.length || 0} station(s)</div>}
    </div>
  );
}

function Big({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="card p-8">
      <div className="text-2xl text-muted uppercase tracking-wider">{label}</div>
      <div className="text-7xl font-black tabular mt-2">{value}</div>
      {sub && <div className="text-2xl text-muted mt-2">{sub}</div>}
    </div>
  );
}

function Crowd({ d }: { d: any }) {
  if (!d) return null;
  const max = Math.max(1, ...(d.histogram || []).map((h: any) => h.count));
  return (
    <div className="h-full flex flex-col gap-8">
      <h2 className="text-6xl font-extrabold">The crowd, measured</h2>
      <div className="grid grid-cols-4 gap-6">
        <Big label="Participants" value={fmtNum(d.participants)} sub={`${d.finished} finished every station`} />
        <Big label="Steps counted" value={fmtNum(d.total_steps)} sub="by the accelerometers" />
        <Big label="Distance walked" value={fmtM(d.total_distance_m)} sub="all participants" />
        <Big label="Average time" value={fmtTime(d.avg_time_s, 0)} sub={d.best_time_s ? `best ${fmtTime(d.best_time_s)}` : ""} />
      </div>
      <div className="card p-8 flex-1 flex flex-col">
        <div className="text-2xl text-muted mb-4">Finishing times</div>
        <div className="flex-1 flex items-end gap-3">
          {(d.histogram || []).map((h: any, k: number) => (
            <div key={k} className="flex-1 flex flex-col items-center justify-end h-full">
              <div className="text-2xl font-bold mb-2">{h.count || ""}</div>
              <div className="w-full bg-brand rounded-t-lg" style={{ height: `${(h.count / max) * 80}%` }} />
              <div className="text-xl text-muted mt-2 tabular">{fmtTime(h.from, 0)}</div>
            </div>
          ))}
        </div>
      </div>
      {d.station_orders?.length > 0 && (
        <div className="text-2xl text-muted">Most common order: <b className="text-text">{d.station_orders[0].order}</b>. Shortest possible: <b className="text-accent">{d.optimal_order}</b></div>
      )}
    </div>
  );
}

function HeatPanel({ d, course }: { d: any; course: any }) {
  if (!d || !course?.data) return <CoursePanel course={course} />;
  const cd = course.data;
  return (
    <div className="h-full grid grid-cols-[2fr_1fr] gap-8">
      <CourseMap big courseId={course.id} booth={cd.booth} stations={cd.stations} background={cd.background}
        heat={{ cell_m: d.heat.cell_m, cells: d.heat.cells.map((c: any) => ({ i: c.i, j: c.j, value: c.n })) }} height={900} />
      <div className="flex flex-col gap-6 justify-center">
        <h2 className="text-6xl font-extrabold">Where everyone walked</h2>
        <div className="text-3xl text-muted">Every participant's track, layered. Brighter means more people passed through.</div>
        <Big label="Tracks" value={fmtNum(d.participants)} />
      </div>
    </div>
  );
}

function EnvPanel({ d, course }: { d: any; course: any }) {
  const [metric, setMetric] = useState<"temperature" | "humidity" | "lux">("temperature");
  useEffect(() => {
    const id = setInterval(() => setMetric((m) => (m === "temperature" ? "humidity" : m === "humidity" ? "lux" : "temperature")), 5000);
    return () => clearInterval(id);
  }, []);
  if (!d || !course?.data) return <CoursePanel course={course} />;
  const cells = d.environment.cells.filter((c: any) => c[metric] != null);
  const vals = cells.map((c: any) => c[metric]);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const label = { temperature: "Temperature", humidity: "Humidity", lux: "Light" }[metric];
  const unit = { temperature: "°C", humidity: "% RH", lux: "lux" }[metric];
  const cd = course.data;
  return (
    <div className="h-full grid grid-cols-[2fr_1fr] gap-8">
      <CourseMap big courseId={course.id} booth={cd.booth} stations={cd.stations} background={cd.background} height={900}
        envCells={{ cell_m: d.environment.cell_m, cells: cells.map((c: any) => ({ i: c.i, j: c.j, value: c[metric] })), colorFor: (v) => turbo((v - lo) / (hi - lo || 1)) }} />
      <div className="flex flex-col gap-6 justify-center">
        <h2 className="text-6xl font-extrabold">The show floor: {label}</h2>
        <div className="text-3xl text-muted">Averaged from every participant's sensor as they walked. A crowd-sourced map of the venue.</div>
        {vals.length > 0 && <div className="text-5xl font-black tabular">{lo.toFixed(1)} to {hi.toFixed(1)} {unit}</div>}
        <div className="h-6 rounded" style={{ background: `linear-gradient(90deg, ${[0, .25, .5, .75, 1].map((x) => turbo(x)).join(",")})` }} />
      </div>
    </div>
  );
}

function CoursePanel({ course }: { course: any }) {
  if (!course?.data) return <div className="text-5xl text-muted">Ask at the booth to join the hunt!</div>;
  const cd = course.data;
  return (
    <div className="h-full grid grid-cols-[2fr_1fr] gap-8">
      <CourseMap big courseId={course.id} booth={cd.booth} stations={cd.stations} background={cd.background} height={900}
        reference={{ x: cd.route.x, y: cd.route.y, source: cd.route.source, opacity: 0.5 }} />
      <div className="flex flex-col gap-6 justify-center">
        <h2 className="text-6xl font-extrabold">The course</h2>
        <div className="text-3xl text-muted">{cd.stations.length} stations. Rest the sensor still for 10 seconds at each one.</div>
        <Big label="Crew par" value={fmtTime(cd.par.par_time_s, 0)} sub="can you beat it?" />
      </div>
    </div>
  );
}

function StoryPanel({ rec }: { rec: any }) {
  const a = useApi<any>(`/api/recordings/${rec.id}/analysis`);
  const st = a.data?.story;
  if (!st) return null;
  return (
    <div className="h-full flex flex-col gap-6">
      <div>
        <div className="text-2xl text-accent uppercase tracking-widest font-bold">What the sensor recorded</div>
        <h2 className="text-6xl font-extrabold">{rec.title}</h2>
      </div>
      <div className="grid grid-cols-[3fr_2fr] gap-8 flex-1 min-h-0">
        <ol className="space-y-3 overflow-hidden">
          {st.timeline.slice(0, 7).map((h: any, k: number) => (
            <li key={k} className="flex gap-6 items-baseline">
              <span className="text-4xl font-black tabular text-brand w-28 text-right">{h.time}</span>
              <span><span className="text-4xl font-bold">{h.title}</span><div className="text-2xl text-muted">{h.detail}</div></span>
            </li>
          ))}
        </ol>
        <div className="space-y-4">
          {st.facts.slice(0, 5).map((h: any, k: number) => (
            <div key={k} className="card p-5"><div className="text-3xl font-bold">{h.title}</div><div className="text-xl text-muted">{h.detail}</div></div>
          ))}
        </div>
      </div>
    </div>
  );
}
