"use client";
import { use, useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api";

const DEFAULTS = [47, 73, 113, 157, 199, 241, 283, 331];

/** Vibration beacon: plays a station-specific tone through a speaker or transducer under the station marker. */
export default function Beacon({ params }: { params: Promise<{ stationId: string }> }) {
  const { stationId } = use(params);
  const course = useApi<any>("/api/courses/active");
  const st = course.data?.data?.stations?.find((s: any) => s.id === stationId || String(s.number) === stationId);
  const num = st?.number ?? (parseInt(stationId.replace(/\D/g, "")) || 1);
  const freq = st?.beacon_hz || DEFAULTS[(num - 1) % DEFAULTS.length];
  const [on, setOn] = useState(false);
  const [vol, setVol] = useState(0.8);
  const ctx = useRef<AudioContext | null>(null);
  const osc = useRef<OscillatorNode | null>(null);
  const gain = useRef<GainNode | null>(null);

  useEffect(() => { if (gain.current) gain.current.gain.value = vol; }, [vol]);
  useEffect(() => () => { osc.current?.stop(); ctx.current?.close(); }, []);

  const toggle = () => {
    if (on) { osc.current?.stop(); osc.current = null; setOn(false); return; }
    ctx.current = ctx.current || new AudioContext();
    const o = ctx.current.createOscillator();
    const g = ctx.current.createGain();
    o.type = "sine"; o.frequency.value = freq; g.gain.value = vol;
    o.connect(g).connect(ctx.current.destination);
    o.start();
    osc.current = o; gain.current = g; setOn(true);
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-8 text-center p-8">
      <div className="text-3xl text-muted">Vibration beacon</div>
      <div className="text-8xl font-black">{st?.name || `Station ${num}`}</div>
      <div className="text-6xl font-black text-brand tabular">{freq} Hz</div>
      <button className={`btn text-3xl px-12 py-6 ${on ? "btn-danger" : "btn-primary"}`} onClick={toggle}>{on ? "Stop tone" : "Start tone"}</button>
      <label className="flex items-center gap-3 text-xl">Volume <input type="range" min={0} max={1} step={0.05} value={vol} onChange={(e) => setVol(+e.target.value)} /></label>
      <div className="max-w-xl text-muted">Place the speaker or transducer under the station marker so the sensor picks up the tone while it rests. Beacons need the sensor's accelerometer recording at 1000 Hz or faster.</div>
    </div>
  );
}
