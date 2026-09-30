"use client";
import { useEffect, useRef } from "react";
import uPlot from "uplot";

export const PALETTE = ["#00a3e0", "#ffb000", "#3ddc84", "#ff5c5c", "#b48cff", "#4dd0e1", "#f48fb1"];

export type Series = { label: string; color?: string; width?: number; dash?: number[]; fill?: string; points?: boolean; band?: boolean };

type Props = {
  x: number[];
  ys: (number | null)[][];
  series: Series[];
  height?: number;
  xLabel?: string;
  yLabel?: string;
  logX?: boolean;
  logY?: boolean;
  syncKey?: string;
  xRange?: [number, number] | null;
  onZoom?: (min: number, max: number) => void;
  onCursor?: (x: number | null) => void;
  cursorX?: number | null;
  bands?: [number, number][];   // pairs of series indices (1-based) to fill between (min/max envelopes)
  xTime?: boolean;              // format x as m:ss
};

const axisStyle = { stroke: "#9fb0c2", grid: { stroke: "#1f2a36", width: 1 }, ticks: { stroke: "#2a3644", width: 1 } };

function mmss(v: number) {
  const m = Math.floor(v / 60), s = v - m * 60;
  return `${m}:${s.toFixed(s < 10 && m ? 0 : 0).padStart(2, "0")}`;
}

export default function UPlotChart(p: Props) {
  const el = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const cb = useRef({ onZoom: p.onZoom, onCursor: p.onCursor });
  cb.current = { onZoom: p.onZoom, onCursor: p.onCursor };

  useEffect(() => {
    if (!el.current) return;
    const width = el.current.clientWidth || 800;
    const opts: uPlot.Options = {
      width,
      height: p.height ?? 260,
      cursor: { sync: p.syncKey ? { key: p.syncKey, setSeries: false } : undefined, drag: { x: true, y: false } },
      scales: {
        x: { time: false, distr: p.logX ? 3 : 1, ...(p.xRange ? { range: () => p.xRange as [number, number] } : {}) },
        y: { distr: p.logY ? 3 : 1 },
      },
      axes: [
        { ...axisStyle, label: p.xLabel, values: p.xTime ? (_u, vals) => vals.map((v) => (v == null ? "" : mmss(v))) : undefined },
        { ...axisStyle, label: p.yLabel, size: 70,
          values: p.logY ? (_u, vals) => vals.map((v) => (v == null ? "" : v !== 0 && (Math.abs(v) < 0.01 || Math.abs(v) >= 1e4) ? v.toExponential(0) : String(+v.toPrecision(3)))) : undefined },
      ],
      series: [
        { label: p.xLabel || "x", value: p.xTime ? (_u, v) => (v == null ? "--" : mmss(v)) : undefined },
        ...p.series.map((s, i) => ({
          label: s.label, stroke: s.color || PALETTE[i % PALETTE.length], width: s.width ?? 1.5,
          dash: s.dash, fill: s.fill, points: { show: !!s.points },
        })),
      ],
      bands: p.bands?.map(([a, b]) => ({ series: [a, b] as [number, number], fill: "rgba(0,163,224,0.18)" })),
      hooks: {
        setSelect: [(u) => {
          if (u.select.width > 5) {
            const min = u.posToVal(u.select.left, "x"), max = u.posToVal(u.select.left + u.select.width, "x");
            cb.current.onZoom?.(min, max);
          }
        }],
        setCursor: [(u) => {
          const i = u.cursor.idx;
          cb.current.onCursor?.(i == null ? null : (u.data[0][i] as number));
        }],
      },
      legend: { show: true },
    };
    const data = [p.x, ...p.ys] as uPlot.AlignedData;
    plot.current?.destroy();
    plot.current = new uPlot(opts, data, el.current);
    const ro = new ResizeObserver(() => {
      if (el.current && plot.current) plot.current.setSize({ width: el.current.clientWidth, height: p.height ?? 260 });
    });
    ro.observe(el.current);
    return () => { ro.disconnect(); plot.current?.destroy(); plot.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.x, p.ys, p.series.length, p.logX, p.logY, p.height, p.xRange?.[0], p.xRange?.[1]]);

  return <div ref={el} className="w-full" />;
}
