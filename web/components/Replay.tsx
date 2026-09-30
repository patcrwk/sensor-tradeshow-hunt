"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import CourseMap, { Route, Station } from "./CourseMap";
import { fmtTime } from "@/lib/format";

type Track = { t: number[]; x: number[]; y: number[]; source?: string[] | string; t0: number; label: string; color: string };

function interp(tr: Track, t: number) {
  const ts = tr.t;
  if (!ts.length) return null;
  if (t <= ts[0]) return { x: tr.x[0], y: tr.y[0] };
  if (t >= ts[ts.length - 1]) return { x: tr.x[ts.length - 1], y: tr.y[ts.length - 1] };
  let lo = 0, hi = ts.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (ts[m] <= t) lo = m; else hi = m; }
  const f = (t - ts[lo]) / (ts[hi] - ts[lo] || 1);
  return { x: tr.x[lo] + f * (tr.x[hi] - tr.x[lo]), y: tr.y[lo] + f * (tr.y[hi] - tr.y[lo]) };
}

export default function Replay({ main, ghost, courseMap, duration, checkins, big }: {
  main: Track; ghost?: Track | null; duration: number;
  courseMap: { courseId?: number; booth?: any; stations?: Station[]; reference?: Route | null; strays?: any[]; background?: any };
  checkins?: { t: number; station: string }[]; big?: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(20);
  const raf = useRef<number>(0);
  const last = useRef<number>(0);

  useEffect(() => {
    if (!playing) return;
    const tick = (now: number) => {
      const dt = last.current ? (now - last.current) / 1000 : 0;
      last.current = now;
      setElapsed((e) => {
        const n = e + dt * speed;
        if (n >= duration) { setPlaying(false); return duration; }
        return n;
      });
      raf.current = requestAnimationFrame(tick);
    };
    last.current = 0;
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [playing, speed, duration]);

  const cut = (tr: Track): Route => {
    const tEnd = tr.t0 + elapsed;
    const n = tr.t.findIndex((t) => t > tEnd);
    const k = n < 0 ? tr.t.length : n;
    return { x: tr.x.slice(0, k), y: tr.y.slice(0, k), source: Array.isArray(tr.source) ? tr.source.slice(0, k) : tr.source };
  };
  const mp = interp(main, main.t0 + elapsed);
  const gp = ghost ? interp(ghost, ghost.t0 + elapsed) : null;
  const visited = useMemo(() => (checkins || []).filter((c) => c.t <= main.t0 + elapsed).map((c) => c.station), [checkins, elapsed, main.t0]);

  return (
    <div>
      <CourseMap {...courseMap} big={big}
        routes={[...(ghost ? [{ ...cut(ghost), color: ghost.color, opacity: 0.8, width: 3 }] : []), cut(main)]}
        markers={[...(gp ? [{ ...gp, color: ghost!.color, label: ghost!.label }] : []), ...(mp ? [{ ...mp, color: main.color, label: main.label }] : [])]}
        highlight={visited} />
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        <button className="btn btn-primary" onClick={() => { if (elapsed >= duration) setElapsed(0); setPlaying(!playing); }}>
          {playing ? "Pause" : elapsed >= duration ? "Replay" : "Play"}
        </button>
        <input type="range" min={0} max={duration} step={0.5} value={elapsed} className="flex-1 accent-[var(--brand)]"
          onChange={(e) => { setPlaying(false); setElapsed(+e.target.value); }} />
        <span className={`${big ? "text-4xl" : "text-2xl"} font-extrabold tabular w-32 text-right`}>{fmtTime(elapsed)}</span>
        <select className="input w-24" value={speed} onChange={(e) => setSpeed(+e.target.value)}>
          {[5, 10, 20, 40, 80].map((s) => <option key={s} value={s}>{s}x</option>)}
        </select>
      </div>
    </div>
  );
}
