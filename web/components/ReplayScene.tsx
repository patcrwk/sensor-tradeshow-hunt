"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/* Reconstructed 3D replay drawn on a 2D canvas with a small hand-written
   perspective projection (no 3D library). Everything shown comes from the
   replay track the engine builds from the sensor data. The HUD is drawn into
   the canvas so a recorded video includes it. */

type Replay = {
  model: "quadcopter" | "sensor" | string;
  fps: number; duration_s: number; t: number[];
  q?: number[][]; roll?: number[]; pitch?: number[]; yaw?: number[];
  altitude_m?: number[]; activity?: number[]; accel_g?: number[]; temperature_c?: number[];
  x?: number[]; y?: number[];
  events: { t: number; label: string }[];
  story?: { t: number; title: string }[];
  notes: string[];
};
type V3 = [number, number, number];

const W = 1280, H = 720, STRIP = 70;

function lerp(a: number[] | undefined, f: number) {
  if (!a || !a.length) return 0;
  const i = Math.max(0, Math.min(a.length - 1, Math.floor(f)));
  const j = Math.min(a.length - 1, i + 1);
  const k = f - Math.floor(f);
  return a[i] + (a[j] - a[i]) * k;
}

function qAt(q: number[][] | undefined, f: number): number[] {
  if (!q || !q.length) return [1, 0, 0, 0];
  const i = Math.max(0, Math.min(q.length - 1, Math.floor(f)));
  const j = Math.min(q.length - 1, i + 1);
  const k = f - Math.floor(f);
  let b = q[j];
  const d = q[i][0] * b[0] + q[i][1] * b[1] + q[i][2] * b[2] + q[i][3] * b[3];
  if (d < 0) b = b.map((v) => -v);
  const r = q[i].map((v, n) => v + (b[n] - v) * k);
  const m = Math.hypot(...r) || 1;
  return r.map((v) => v / m);
}

function rot(q: number[], v: V3): V3 {
  const [w, x, y, z] = q;
  return [
    (1 - 2 * (y * y + z * z)) * v[0] + 2 * (x * y - w * z) * v[1] + 2 * (x * z + w * y) * v[2],
    2 * (x * y + w * z) * v[0] + (1 - 2 * (x * x + z * z)) * v[1] + 2 * (y * z - w * x) * v[2],
    2 * (x * z - w * y) * v[0] + 2 * (y * z + w * x) * v[1] + (1 - 2 * (x * x + y * y)) * v[2],
  ];
}

const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a: V3): V3 => { const m = Math.hypot(...a) || 1; return [a[0] / m, a[1] / m, a[2] / m]; };

class Cam {
  eye: V3; r: V3; u: V3; f: V3; focal: number; cx: number; cy: number;
  constructor(target: V3, az: number, el: number, dist: number, w: number, h: number) {
    this.eye = add(target, [dist * Math.cos(el) * Math.cos(az), dist * Math.cos(el) * Math.sin(az), dist * Math.sin(el)]);
    this.f = norm(sub(target, this.eye));
    this.r = norm(cross(this.f, [0, 0, 1]));
    this.u = cross(this.r, this.f);
    this.focal = h * 1.1; this.cx = w / 2; this.cy = h / 2;
  }
  cam(p: V3): V3 { const d = sub(p, this.eye); return [dot(d, this.r), dot(d, this.u), dot(d, this.f)]; }
  proj(c: V3): [number, number] { return [this.cx + (this.focal * c[0]) / c[2], this.cy - (this.focal * c[1]) / c[2]]; }
  /** Project a segment, clipped against the near plane. */
  seg(a: V3, b: V3): [number, number, number, number] | null {
    let ca = this.cam(a), cb = this.cam(b);
    const n = 0.2;
    if (ca[2] < n && cb[2] < n) return null;
    if (ca[2] < n) { const t = (n - ca[2]) / (cb[2] - ca[2]); ca = [ca[0] + t * (cb[0] - ca[0]), ca[1] + t * (cb[1] - ca[1]), n]; }
    if (cb[2] < n) { const t = (n - cb[2]) / (ca[2] - cb[2]); cb = [cb[0] + t * (ca[0] - cb[0]), cb[1] + t * (ca[1] - cb[1]), n]; }
    const pa = this.proj(ca), pb = this.proj(cb);
    return [pa[0], pa[1], pb[0], pb[1]];
  }
}

type Prim = { depth: number; draw: (ctx: CanvasRenderingContext2D) => void };

function box(center: V3, half: V3, q: number[], pos: V3, cam: Cam, color: [number, number, number], prims: Prim[]) {
  const [hx, hy, hz] = half;
  const corners: V3[] = [];
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) for (const sz of [-1, 1])
    corners.push(add(pos, rot(q, [center[0] + sx * hx, center[1] + sy * hy, center[2] + sz * hz])));
  const faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]];
  const light = norm([0.4, -0.3, 1]);
  for (const f of faces) {
    const pts = f.map((i) => corners[i]);
    const nrm = norm(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0])));
    const mid: V3 = pts.reduce((a, p) => add(a, [p[0] / 4, p[1] / 4, p[2] / 4]), [0, 0, 0] as V3);
    if (dot(nrm, sub(cam.eye, mid)) <= 0) continue;          // back face
    const cs = pts.map((p) => cam.cam(p));
    if (cs.some((c) => c[2] < 0.2)) continue;
    const shade = 0.45 + 0.55 * Math.max(0, dot(nrm, light));
    const fill = `rgb(${color.map((c) => Math.round(c * shade)).join(",")})`;
    prims.push({ depth: cs.reduce((a, c) => a + c[2], 0) / 4, draw: (ctx) => {
      ctx.beginPath();
      cs.forEach((c, i) => { const p = cam.proj(c); if (i) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); });
      ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = "rgba(0,0,0,.35)"; ctx.lineWidth = 1; ctx.stroke();
    } });
  }
}

function line3(a: V3, b: V3, cam: Cam, color: string, width: number, prims: Prim[]) {
  const s = cam.seg(a, b);
  if (!s) return;
  const depth = (cam.cam(a)[2] + cam.cam(b)[2]) / 2;
  prims.push({ depth, draw: (ctx) => {
    ctx.beginPath(); ctx.moveTo(s[0], s[1]); ctx.lineTo(s[2], s[3]);
    ctx.strokeStyle = color; ctx.lineWidth = width * (6 / Math.max(depth, 1)); ctx.lineCap = "round"; ctx.stroke();
  } });
}

function disc(center: V3, radius: number, q: number[], pos: V3, cam: Cam, fill: string, prims: Prim[], blades?: { angle: number; color: string }) {
  const pts: [number, number][] = [];
  let depth = 0;
  for (let k = 0; k < 24; k++) {
    const a = (k / 24) * Math.PI * 2;
    const c = cam.cam(add(pos, rot(q, [center[0] + radius * Math.cos(a), center[1] + radius * Math.sin(a), center[2]])));
    if (c[2] < 0.2) return;
    depth += c[2] / 24;
    pts.push(cam.proj(c));
  }
  const bl: [number, number, number, number][] = [];
  if (blades) for (const off of [0, Math.PI]) {
    const a = blades.angle + off;
    const p1 = cam.proj(cam.cam(add(pos, rot(q, center))));
    const p2 = cam.proj(cam.cam(add(pos, rot(q, [center[0] + radius * 0.95 * Math.cos(a), center[1] + radius * 0.95 * Math.sin(a), center[2]]))));
    bl.push([p1[0], p1[1], p2[0], p2[1]]);
  }
  prims.push({ depth: depth - 0.01, draw: (ctx) => {
    ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath();
    ctx.fillStyle = fill; ctx.fill(); ctx.strokeStyle = "rgba(255,255,255,.35)"; ctx.lineWidth = 1; ctx.stroke();
    if (blades) { ctx.strokeStyle = blades.color; ctx.lineWidth = 3; ctx.lineCap = "round"; bl.forEach((b) => { ctx.beginPath(); ctx.moveTo(b[0], b[1]); ctx.lineTo(b[2], b[3]); ctx.stroke(); }); }
  } });
}

function buildModel(model: string, q: number[], pos: V3, cam: Cam, act: number, t: number, prims: Prim[]) {
  if (model === "quadcopter") {
    const arm = 0.62;
    const rotors: V3[] = [[arm, arm, 0.06], [arm, -arm, 0.06], [-arm, arm, 0.06], [-arm, -arm, 0.06]];
    rotors.forEach((r, i) => {
      const front = r[0] > 0;
      line3(add(pos, rot(q, [0, 0, 0])), add(pos, rot(q, r)), cam, front ? "#ffb000" : "#8fa3b8", 2.2, prims);
      box(r, [0.05, 0.05, 0.05], q, pos, cam, [70, 80, 95], prims);
      const spin = act > 0.08;
      disc([r[0], r[1], r[2] + 0.07], 0.38, q, pos, cam,
        spin ? `rgba(0,163,224,${0.12 + 0.35 * Math.min(act, 1)})` : "rgba(160,175,190,.10)", prims,
        { angle: (spin ? t * (40 + 60 * act) : 0.4) * (i % 2 ? -1 : 1) + i, color: spin ? "rgba(255,255,255,.55)" : "#cfd8e3" });
    });
    box([0, 0, 0], [0.28, 0.2, 0.09], q, pos, cam, [40, 52, 66], prims);
    box([0.1, 0, 0.13], [0.12, 0.09, 0.04], q, pos, cam, [0, 140, 200], prims);   // sensor on top
    box([0.3, 0, -0.02], [0.03, 0.08, 0.05], q, pos, cam, [255, 176, 0], prims);   // front marker
  } else {
    box([0, 0, 0], [0.55, 0.38, 0.22], q, pos, cam, [0, 140, 200], prims);
    box([0.2, 0, 0.23], [0.2, 0.2, 0.01], q, pos, cam, [20, 30, 40], prims);
    const axes: [V3, string][] = [[[1.0, 0, 0], "#ff5c5c"], [[0, 0.85, 0], "#3ddc84"], [[0, 0, 0.7], "#4d9bff"]];
    axes.forEach(([a, c]) => line3(pos, add(pos, rot(q, a)), cam, c, 1.6, prims));
  }
}

export default function ReplayScene({ data, title }: { data: Replay; title: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);
  const [view, setView] = useState({ az: -2.2, el: 0.32, dist: 5.5, follow: false });
  const [recording, setRecording] = useState(false);
  const recRef = useRef<MediaRecorder | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const tRef = useRef(0);
  tRef.current = t;

  const dur = data.duration_s;
  const hasGps = !!data.x;
  const altMax = Math.max(1, ...(data.altitude_m || [0]));
  const altMin = Math.min(0, ...(data.altitude_m || [0]));

  const draw = useCallback((time: number) => {
    const cv = canvas.current;
    if (!cv) return;
    const ctx = cv.getContext("2d")!;
    const f = time * data.fps;
    const q = qAt(data.q, f);
    const alt = lerp(data.altitude_m, f);
    const px = hasGps ? lerp(data.x, f) : 0, py = hasGps ? lerp(data.y, f) : 0;
    const pos: V3 = [px, py, Math.max(alt, altMin) + 0.6];
    const yawRad = ((data.yaw ? lerp(data.yaw, f) : 0) * Math.PI) / 180;
    const az = view.follow ? yawRad + Math.PI : view.az;
    const sceneH = H - STRIP;
    const cam = new Cam(pos, az, view.el, view.dist, W, sceneH);

    // sky and ground
    const sky = ctx.createLinearGradient(0, 0, 0, sceneH);
    sky.addColorStop(0, "#0b1624"); sky.addColorStop(1, "#16263a");
    ctx.fillStyle = sky; ctx.fillRect(0, 0, W, H);

    // ground grid (5 m cells) around the object; converging lines show height
    const g0: V3 = [Math.round(px / 5) * 5, Math.round(py / 5) * 5, 0];
    ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W, sceneH); ctx.clip();
    for (let k = -30; k <= 30; k++) {
      const major = (k + Math.round(g0[0] / 5)) % 5 === 0;
      for (const dir of [0, 1]) {
        const a: V3 = dir ? [g0[0] - 150, g0[1] + k * 5, 0] : [g0[0] + k * 5, g0[1] - 150, 0];
        const b: V3 = dir ? [g0[0] + 150, g0[1] + k * 5, 0] : [g0[0] + k * 5, g0[1] + 150, 0];
        const s = cam.seg(a, b);
        if (!s) continue;
        ctx.strokeStyle = major ? "rgba(120,160,200,.35)" : "rgba(120,160,200,.14)";
        ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(s[0], s[1]); ctx.lineTo(s[2], s[3]); ctx.stroke();
      }
    }
    // take-off pad and shadow
    const shadow: V3 = [px, py, 0];
    const pad = cam.seg([-1, 0, 0], [1, 0, 0]);
    if (pad) { ctx.strokeStyle = "#ffb000"; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(pad[0], pad[1]); ctx.lineTo(pad[2], pad[3]); ctx.stroke(); }
    const pad2 = cam.seg([0, -1, 0], [0, 1, 0]);
    if (pad2) { ctx.beginPath(); ctx.moveTo(pad2[0], pad2[1]); ctx.lineTo(pad2[2], pad2[3]); ctx.stroke(); }
    const sh = cam.cam(shadow);
    if (sh[2] > 0.2) {
      const p = cam.proj(sh);
      ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.beginPath(); ctx.ellipse(p[0], p[1], 260 / sh[2] * 1.4, 90 / sh[2] * 1.4, 0, 0, Math.PI * 2); ctx.fill();
    }
    // height line
    const hl = cam.seg(shadow, [px, py, pos[2]]);
    if (hl) { ctx.setLineDash([6, 6]); ctx.strokeStyle = "rgba(255,255,255,.35)"; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(hl[0], hl[1]); ctx.lineTo(hl[2], hl[3]); ctx.stroke(); ctx.setLineDash([]); }
    // trail (last 30 s)
    const trailStart = Math.max(0, f - 30 * data.fps);
    ctx.strokeStyle = "rgba(0,163,224,.6)"; ctx.lineWidth = 2; ctx.beginPath();
    let started = false;
    for (let k = trailStart; k <= f; k += data.fps / 4) {
      const pp: V3 = [hasGps ? lerp(data.x, k) : 0, hasGps ? lerp(data.y, k) : 0, Math.max(lerp(data.altitude_m, k), altMin) + 0.6];
      const c = cam.cam(pp);
      if (c[2] < 0.3) { started = false; continue; }
      const p = cam.proj(c);
      if (started) ctx.lineTo(p[0], p[1]); else { ctx.moveTo(p[0], p[1]); started = true; }
    }
    ctx.stroke();

    const prims: Prim[] = [];
    buildModel(data.model, q, pos, cam, lerp(data.activity, f), time, prims);
    prims.sort((a, b) => b.depth - a.depth).forEach((p) => p.draw(ctx));
    ctx.restore();

    // HUD
    const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
    ctx.fillStyle = "rgba(11,15,20,.72)"; ctx.fillRect(16, 16, 330, 54); ctx.fillRect(W - 276, 16, 260, 196);
    ctx.fillStyle = "#f2f5f8"; ctx.font = "700 26px system-ui"; ctx.fillText(title, 30, 52);
    ctx.textAlign = "right"; ctx.fillStyle = "#9fb0c2"; ctx.font = "600 22px system-ui"; ctx.fillText(fmt(time), 334, 52);
    ctx.textAlign = "left";
    const rows: [string, string][] = [];
    if (data.altitude_m) rows.push(["HEIGHT", `${alt.toFixed(1)} m`]);
    if (data.roll) rows.push(["ROLL / PITCH", `${lerp(data.roll, f).toFixed(0)}° / ${lerp(data.pitch, f).toFixed(0)}°`]);
    if (data.yaw) rows.push(["HEADING TURNED", `${(lerp(data.yaw, f) - data.yaw[0]).toFixed(0)}°`]);
    if (data.accel_g) rows.push(["ACCELERATION", `${lerp(data.accel_g, f).toFixed(1)} g`]);
    if (data.temperature_c) rows.push(["TEMPERATURE", `${lerp(data.temperature_c, f).toFixed(1)} °C`]);
    rows.forEach(([k, v], i) => {
      ctx.fillStyle = "#9fb0c2"; ctx.font = "600 13px system-ui"; ctx.fillText(k, W - 260, 44 + i * 34);
      ctx.fillStyle = "#f2f5f8"; ctx.font = "800 22px system-ui"; ctx.textAlign = "right"; ctx.fillText(v, W - 30, 46 + i * 34); ctx.textAlign = "left";
    });
    if (data.activity) {
      const a = Math.min(lerp(data.activity, f), 1);
      ctx.fillStyle = "#9fb0c2"; ctx.font = "600 13px system-ui";
      ctx.fillText(data.model === "quadcopter" ? "MOTORS (VIBRATION)" : "VIBRATION", 30, 100);
      ctx.fillStyle = "rgba(255,255,255,.1)"; ctx.fillRect(30, 108, 220, 12);
      ctx.fillStyle = "#00a3e0"; ctx.fillRect(30, 108, 220 * a, 12);
    }
    // captions: story items and shock events near the current time
    const cap = [...(data.story || []).map((s) => ({ t: s.t, text: s.title, c: "#f2f5f8" })),
      ...data.events.map((e) => ({ t: e.t, text: `Shock ${e.label}`, c: "#ffb000" }))]
      .filter((c) => time >= c.t && time - c.t < 4 * Math.max(speed / 5, 1)).sort((a, b) => b.t - a.t)[0];
    if (cap) {
      ctx.font = "800 34px system-ui"; ctx.textAlign = "center";
      const w = ctx.measureText(cap.text).width + 50;
      ctx.fillStyle = "rgba(11,15,20,.78)"; ctx.fillRect(W / 2 - w / 2, sceneH - 84, w, 54);
      ctx.fillStyle = cap.c; ctx.fillText(cap.text, W / 2, sceneH - 45); ctx.textAlign = "left";
    }
    ctx.fillStyle = "rgba(242,245,248,.55)"; ctx.font = "13px system-ui";
    ctx.fillText(`Reconstructed from sensor data. Model not to scale.${hasGps ? "" : " No GPS: shown in place."}`, 30, sceneH - 14);

    // bottom strip: height profile with events and cursor
    ctx.fillStyle = "#0e141b"; ctx.fillRect(0, sceneH, W, STRIP);
    if (data.altitude_m) {
      ctx.strokeStyle = "#00a3e0"; ctx.lineWidth = 2; ctx.beginPath();
      const n = data.altitude_m.length, stepN = Math.max(1, Math.floor(n / W));
      for (let i = 0; i < n; i += stepN) {
        const xx = 20 + ((W - 40) * data.t[i]) / dur;
        const yy = sceneH + STRIP - 10 - ((STRIP - 22) * (data.altitude_m[i] - altMin)) / (altMax - altMin);
        if (i) ctx.lineTo(xx, yy); else ctx.moveTo(xx, yy);
      }
      ctx.stroke();
    }
    data.events.forEach((e) => { const xx = 20 + ((W - 40) * e.t) / dur; ctx.fillStyle = "#ffb000"; ctx.fillRect(xx - 1, sceneH + 8, 2, 10); });
    const cx = 20 + ((W - 40) * time) / dur;
    ctx.fillStyle = "#fff"; ctx.fillRect(cx - 1, sceneH + 4, 2, STRIP - 8);
  }, [data, view, title, speed, hasGps, altMax, altMin, dur]);

  useEffect(() => { draw(t); }, [t, draw]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0, last = 0;
    const tick = (now: number) => {
      const dt = last ? (now - last) / 1000 : 0;
      last = now;
      const nt = tRef.current + dt * speed;
      if (nt >= dur) {
        setT(dur); setPlaying(false);
        if (recRef.current?.state === "recording") recRef.current.stop();
        return;
      }
      setT(nt);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, dur]);

  const record = () => {
    const cv = canvas.current;
    if (!cv || typeof MediaRecorder === "undefined") { alert("This browser cannot record video."); return; }
    const type = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm", "video/mp4"].find((m) => MediaRecorder.isTypeSupported(m));
    const rec = new MediaRecorder(cv.captureStream(30), type ? { mimeType: type, videoBitsPerSecond: 6_000_000 } : undefined);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = () => {
      setRecording(false);
      const blob = new Blob(chunks, { type: rec.mimeType || "video/webm" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${title.replace(/\W+/g, "_").toLowerCase()}_replay.${(rec.mimeType || "").includes("mp4") ? "mp4" : "webm"}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    };
    recRef.current = rec;
    if (t >= dur - 0.5) setT(0);
    rec.start(500);
    setRecording(true);
    setPlaying(true);
  };

  return (
    <div>
      <canvas ref={canvas} width={W} height={H} className="w-full rounded-lg bg-black cursor-grab"
        onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY }; (e.target as Element).setPointerCapture(e.pointerId); }}
        onPointerMove={(e) => {
          if (!drag.current) return;
          const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y;
          drag.current = { x: e.clientX, y: e.clientY };
          setView((v) => ({ ...v, follow: false, az: v.az - dx * 0.008, el: Math.max(-0.1, Math.min(1.45, v.el + dy * 0.006)) }));
        }}
        onPointerUp={() => (drag.current = null)}
        onWheel={(e) => setView((v) => ({ ...v, dist: Math.max(2.5, Math.min(60, v.dist * (e.deltaY > 0 ? 1.1 : 0.9))) }))}
        onClick={(e) => {
          const r = (e.target as HTMLCanvasElement).getBoundingClientRect();
          const y = ((e.clientY - r.top) / r.height) * H;
          if (y > H - STRIP) { setT(Math.max(0, Math.min(dur, (((e.clientX - r.left) / r.width) * W - 20) / (W - 40) * dur))); }
        }} />
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        <button className="btn btn-primary" disabled={recording} onClick={() => { if (t >= dur) setT(0); setPlaying(!playing); }}>{playing ? "Pause" : t >= dur ? "Replay" : "Play"}</button>
        <input type="range" min={0} max={dur} step={0.1} value={t} className="flex-1 min-w-[200px]" disabled={recording}
          onChange={(e) => { setPlaying(false); setT(+e.target.value); }} />
        <select className="input w-24" value={speed} disabled={recording} onChange={(e) => setSpeed(+e.target.value)}>
          {[1, 2, 5, 10, 20].map((s) => <option key={s} value={s}>{s}x</option>)}
        </select>
        <button className={`btn ${view.follow ? "btn-primary" : ""}`} onClick={() => setView((v) => ({ ...v, follow: !v.follow }))}>Chase camera</button>
        <button className="btn" onClick={() => setView({ az: -2.2, el: 0.32, dist: 5.5, follow: false })}>Reset view</button>
        {recording
          ? <button className="btn btn-danger" onClick={() => { recRef.current?.stop(); setPlaying(false); }}>Stop and save video</button>
          : <button className="btn" onClick={record}>Record video</button>}
      </div>
      <div className="text-xs text-muted mt-2">Drag to orbit, scroll to zoom, click the height strip to jump. Recording plays from the current point to the end at the chosen speed and saves a video file.</div>
      <ul className="text-sm text-muted mt-3 list-disc ml-5 space-y-1">{data.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
    </div>
  );
}
