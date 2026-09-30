"use client";
import { useMemo, useRef, useState } from "react";
import { apiBase } from "@/lib/api";

export type Station = { id: string; name: string; number: number; x: number; y: number; accuracy_m?: number | null; required?: boolean };
export type Route = { x: number[]; y: number[]; source?: string[] | string; color?: string; opacity?: number; width?: number; label?: string; dashed?: boolean };
export type Marker = { x: number; y: number; color: string; label?: string; r?: number };
export type Cell = { i: number; j: number; value: number };

type Props = {
  courseId?: number;
  booth?: { x: number; y: number } | null;
  stations?: Station[];
  reference?: Route | null;
  routes?: Route[];
  strays?: { x: number; y: number; label?: string }[];
  markers?: Marker[];
  heat?: { cell_m: number; cells: Cell[] } | null;
  envCells?: { cell_m: number; cells: Cell[]; colorFor: (v: number) => string } | null;
  background?: { transform?: { matrix: number[][] } | null; width?: number; height?: number } | null;
  matchRadius?: number | null;
  highlight?: string[];
  editable?: boolean;
  onStationMove?: (id: string, x: number, y: number) => void;
  onMapClick?: (x: number, y: number) => void;
  height?: number;
  showAccuracy?: boolean;
  big?: boolean;
};

const SRC_STYLE: Record<string, { color: string; dash?: string }> = {
  gps: { color: "var(--gps)" },
  fused: { color: "var(--fused)" },
  reconstructed: { color: "var(--recon)", dash: "6 5" },
  straight: { color: "#8898aa", dash: "3 6" },
};

function niceStep(span: number, target = 6) {
  const raw = span / target;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 5, 10]) if (m * p >= raw) return m * p;
  return 10 * p;
}

export default function CourseMap(p: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ id: string; x: number; y: number } | null>(null);
  const W = 1000;
  const pad = p.big ? 50 : 40;

  const { k, minx, maxy, H } = useMemo(() => {
    const xs: number[] = [], ys: number[] = [];
    const add = (x: number, y: number) => { if (isFinite(x) && isFinite(y)) { xs.push(x); ys.push(y); } };
    if (p.booth) add(p.booth.x, p.booth.y);
    p.stations?.forEach((s) => add(s.x, s.y));
    [p.reference, ...(p.routes || [])].forEach((r) => r?.x.forEach((x, i) => add(x, r.y[i])));
    p.strays?.forEach((s) => add(s.x, s.y));
    if (!xs.length) { xs.push(-50, 50); ys.push(-50, 50); }
    let minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
    const m = Math.max(maxx - minx, maxy - miny) * 0.08 + 8;
    minx -= m; maxx += m; miny -= m; maxy += m;
    const spanx = Math.max(maxx - minx, 20), spany = Math.max(maxy - miny, 20);
    const k = (W - 2 * pad) / spanx;
    const H = Math.min(Math.max(spany * k + 2 * pad, 300), 1400);
    return { k: Math.min(k, (H - 2 * pad) / spany), minx, maxy, H };
  }, [p.booth, p.stations, p.reference, p.routes, p.strays, pad]);

  const sx = (x: number) => pad + (x - minx) * k;
  const sy = (y: number) => pad + (maxy - y) * k;
  const toWorld = (cx: number, cy: number) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint();
    pt.x = cx; pt.y = cy;
    const q = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: (q.x - pad) / k + minx, y: maxy - (q.y - pad) / k };
  };

  const step = niceStep((W - 2 * pad) / k);
  const gridX: number[] = [], gridY: number[] = [];
  for (let x = Math.ceil(minx / step) * step; x < minx + (W - 2 * pad) / k; x += step) gridX.push(x);
  for (let y = Math.floor(maxy / step) * step; y > maxy - (H - 2 * pad) / k; y -= step) gridY.push(y);
  const scaleM = niceStep((W - 2 * pad) / k, 5);

  const bgTransform = useMemo(() => {
    const M = p.background?.transform?.matrix;
    if (!M) return null;
    const [[a, b, c], [d, e, f]] = M;
    const det = a * e - b * d;
    if (!det) return null;
    const A = e / det, B = -d / det, C = -b / det, D = a / det, E = (-e * c + b * f) / det, F = (d * c - a * f) / det;
    const tx = pad - minx * k, ty = pad + maxy * k;
    return `matrix(${k * A},${-k * B},${k * C},${-k * D},${k * E + tx},${-k * F + ty})`;
  }, [p.background, k, minx, maxy, pad]);

  const fs = p.big ? 22 : 15;
  const stationR = p.big ? 20 : 14;

  return (
    <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none rounded-lg"
      style={{ background: "#0e141b", maxHeight: p.height }}
      onPointerMove={(e) => {
        if (!drag) return;
        const w = toWorld(e.clientX, e.clientY);
        setDrag({ ...drag, x: w.x, y: w.y });
      }}
      onPointerUp={() => {
        if (drag) p.onStationMove?.(drag.id, Math.round(drag.x * 100) / 100, Math.round(drag.y * 100) / 100);
        setDrag(null);
      }}
      onClick={(e) => { if (p.onMapClick && !drag) { const w = toWorld(e.clientX, e.clientY); p.onMapClick(w.x, w.y); } }}>
      {bgTransform && p.courseId && (
        <image href={`${apiBase()}/api/courses/${p.courseId}/background`} x={0} y={0}
          width={p.background?.width} height={p.background?.height} transform={bgTransform} opacity={0.55}
          preserveAspectRatio="none" />
      )}
      {gridX.map((x) => <line key={"gx" + x} x1={sx(x)} x2={sx(x)} y1={0} y2={H} stroke="#1f2a36" strokeWidth={1} />)}
      {gridY.map((y) => <line key={"gy" + y} y1={sy(y)} y2={sy(y)} x1={0} x2={W} stroke="#1f2a36" strokeWidth={1} />)}

      {p.heat && (() => {
        const max = Math.max(1, ...p.heat.cells.map((c) => c.value));
        return p.heat.cells.map((c) => (
          <rect key={`h${c.i},${c.j}`} x={sx(c.i * p.heat!.cell_m)} y={sy((c.j + 1) * p.heat!.cell_m)}
            width={p.heat!.cell_m * k + 0.5} height={p.heat!.cell_m * k + 0.5}
            fill="var(--accent)" opacity={0.12 + 0.75 * (c.value / max)} />
        ));
      })()}
      {p.envCells && p.envCells.cells.map((c) => (
        <rect key={`e${c.i},${c.j}`} x={sx(c.i * p.envCells!.cell_m)} y={sy((c.j + 1) * p.envCells!.cell_m)}
          width={p.envCells!.cell_m * k + 0.5} height={p.envCells!.cell_m * k + 0.5}
          fill={p.envCells!.colorFor(c.value)} opacity={0.85} />
      ))}

      {p.reference && <RoutePath r={{ ...p.reference, opacity: p.reference.opacity ?? 0.35, width: p.reference.width ?? 3 }} sx={sx} sy={sy} />}
      {p.routes?.map((r, i) => <RoutePath key={i} r={r} sx={sx} sy={sy} />)}

      {p.stations?.map((s) => {
        const x = drag?.id === s.id ? drag.x : s.x;
        const y = drag?.id === s.id ? drag.y : s.y;
        const hi = p.highlight?.includes(s.id);
        return (
          <g key={s.id}>
            {p.showAccuracy && s.accuracy_m ? <circle cx={sx(x)} cy={sy(y)} r={s.accuracy_m * k} fill="var(--brand)" opacity={0.12} /> : null}
            {p.matchRadius ? <circle cx={sx(x)} cy={sy(y)} r={p.matchRadius * k} fill="none" stroke="var(--brand)" strokeDasharray="4 4" opacity={0.5} /> : null}
            <circle cx={sx(x)} cy={sy(y)} r={stationR} fill={hi ? "var(--good)" : s.required === false ? "#3a4656" : "var(--brand)"}
              stroke="#fff" strokeWidth={2} style={{ cursor: p.editable ? "grab" : "default" }}
              onPointerDown={(e) => { if (p.editable) { e.stopPropagation(); (e.target as Element).setPointerCapture?.(e.pointerId); setDrag({ id: s.id, x: s.x, y: s.y }); } }} />
            <text x={sx(x)} y={sy(y) + fs * 0.35} textAnchor="middle" fontSize={fs} fontWeight={800} fill="#001018" pointerEvents="none">{s.number}</text>
            <text x={sx(x)} y={sy(y) + stationR + fs + 2} textAnchor="middle" fontSize={fs * 0.85} fill="#dfe8f1" pointerEvents="none"
              style={{ paintOrder: "stroke", stroke: "#0e141b", strokeWidth: 4 }}>{s.name}</text>
          </g>
        );
      })}
      {p.booth && (
        <g>
          <rect x={sx(p.booth.x) - stationR} y={sy(p.booth.y) - stationR} width={stationR * 2} height={stationR * 2} rx={4}
            fill="var(--accent)" stroke="#fff" strokeWidth={2} />
          <text x={sx(p.booth.x)} y={sy(p.booth.y) + stationR + fs + 2} textAnchor="middle" fontSize={fs * 0.85} fontWeight={700} fill="var(--accent)"
            style={{ paintOrder: "stroke", stroke: "#0e141b", strokeWidth: 4 }}>BOOTH</text>
        </g>
      )}
      {p.strays?.map((s, i) => (
        <g key={"s" + i}>
          <path d={`M ${sx(s.x) - 7} ${sy(s.y) - 7} L ${sx(s.x) + 7} ${sy(s.y) + 7} M ${sx(s.x) + 7} ${sy(s.y) - 7} L ${sx(s.x) - 7} ${sy(s.y) + 7}`}
            stroke="var(--bad)" strokeWidth={3} />
          {s.label && <text x={sx(s.x) + 10} y={sy(s.y) - 8} fontSize={fs * 0.75} fill="var(--bad)">{s.label}</text>}
        </g>
      ))}
      {p.markers?.map((m, i) => (
        <g key={"m" + i}>
          <circle cx={sx(m.x)} cy={sy(m.y)} r={m.r ?? (p.big ? 13 : 9)} fill={m.color} stroke="#fff" strokeWidth={3} />
          {m.label && <text x={sx(m.x) + 14} y={sy(m.y) + 5} fontSize={fs} fontWeight={700} fill={m.color}
            style={{ paintOrder: "stroke", stroke: "#0e141b", strokeWidth: 4 }}>{m.label}</text>}
        </g>
      ))}

      {/* scale bar */}
      <g transform={`translate(${pad}, ${H - 18})`}>
        <rect x={0} y={-6} width={scaleM * k} height={6} fill="#dfe8f1" />
        <text x={scaleM * k + 8} y={0} fontSize={13} fill="#dfe8f1">{scaleM} m</text>
      </g>
      {/* north arrow */}
      <g transform={`translate(${W - 30}, 40)`}>
        <path d="M 0 -22 L 9 6 L 0 0 L -9 6 Z" fill="#dfe8f1" />
        <text x={0} y={22} textAnchor="middle" fontSize={13} fontWeight={700} fill="#dfe8f1">N</text>
      </g>
    </svg>
  );
}

function RoutePath({ r, sx, sy }: { r: Route; sx: (x: number) => number; sy: (y: number) => number }) {
  if (!r.x?.length) return null;
  const srcs = Array.isArray(r.source) ? r.source : r.x.map(() => (r.source as string) || "gps");
  const runs: { src: string; d: string }[] = [];
  let cur = "", d = "";
  for (let i = 0; i < r.x.length; i++) {
    const s = srcs[i] || "gps";
    const pt = `${sx(r.x[i]).toFixed(1)} ${sy(r.y[i]).toFixed(1)}`;
    if (s !== cur) {
      if (d) runs.push({ src: cur, d });
      d = (i > 0 ? `M ${sx(r.x[i - 1]).toFixed(1)} ${sy(r.y[i - 1]).toFixed(1)} L ` : "M ") + pt;
      cur = s;
    } else d += ` L ${pt}`;
  }
  if (d) runs.push({ src: cur, d });
  return (
    <g opacity={r.opacity ?? 1}>
      {runs.map((run, i) => {
        const st = SRC_STYLE[run.src] || SRC_STYLE.gps;
        return <path key={i} d={run.d} fill="none" stroke={r.color || st.color} strokeWidth={r.width ?? 3.5}
          strokeDasharray={r.dashed ? "8 6" : st.dash} strokeLinejoin="round" strokeLinecap="round" />;
      })}
    </g>
  );
}

export function RouteLegend() {
  return (
    <div className="flex gap-4 text-sm text-muted flex-wrap">
      <span><span className="inline-block w-6 h-1 align-middle mr-1" style={{ background: "var(--gps)" }} />measured (GPS)</span>
      <span><span className="inline-block w-6 h-1 align-middle mr-1" style={{ background: "var(--fused)" }} />GPS fused with steps</span>
      <span><span className="inline-block w-6 h-0 border-t-2 border-dashed align-middle mr-1" style={{ borderColor: "var(--recon)" }} />reconstructed (steps and heading)</span>
      <span><span className="inline-block w-6 h-0 border-t-2 border-dotted align-middle mr-1" style={{ borderColor: "#8898aa" }} />straight line (no steps)</span>
      <span><span className="text-bad font-bold mr-1">x</span>stray stop</span>
    </div>
  );
}
