"use client";
import { useEffect, useRef } from "react";

/** Spectrogram-style heat map on a canvas. z[row = frequency][col = time]. */
export default function Heatmap({ t, f, z, height = 280 }: { t: number[]; f: number[]; z: number[][]; height?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c || !z.length) return;
    const W = c.clientWidth || 800;
    c.width = W;
    c.height = height;
    const ctx = c.getContext("2d")!;
    const flat = z.flat().filter((v) => isFinite(v));
    const lo = percentile(flat, 0.02), hi = percentile(flat, 0.995);
    const rows = z.length, cols = z[0].length;
    const left = 50, bottom = 24, pw = W - left - 8, ph = height - bottom - 6;
    ctx.fillStyle = "#0e141b";
    ctx.fillRect(0, 0, W, height);
    const cw = pw / cols, rh = ph / rows;
    for (let r = 0; r < rows; r++) {
      for (let q = 0; q < cols; q++) {
        const v = (z[r][q] - lo) / (hi - lo || 1);
        ctx.fillStyle = turbo(Math.max(0, Math.min(1, v)));
        ctx.fillRect(left + q * cw, 6 + ph - (r + 1) * rh, cw + 1, rh + 1);
      }
    }
    ctx.fillStyle = "#9fb0c2";
    ctx.font = "12px system-ui";
    for (const hz of [10, 30, 100, 300, 1000]) {
      const i = f.findIndex((v) => v >= hz);
      if (i < 0) continue;
      const y = 6 + ph - (i + 0.5) * rh;
      ctx.fillText(`${hz} Hz`, 2, y + 4);
    }
    const n = 6;
    for (let i = 0; i <= n; i++) {
      const q = Math.round((i / n) * (cols - 1));
      const s = t[q];
      ctx.fillText(`${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`, left + q * cw - 10, height - 6);
    }
  }, [t, f, z, height]);
  return <canvas ref={ref} className="w-full rounded-lg" style={{ height }} />;
}

function percentile(a: number[], p: number) {
  if (!a.length) return 0;
  const s = [...a].sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.floor(p * s.length))];
}

// Compact approximation of the Turbo colormap
export function turbo(x: number): string {
  const r = 34.61 + x * (1172.33 - x * (10793.56 - x * (33300.12 - x * (38394.49 - x * 14825.05))));
  const g = 23.31 + x * (557.33 + x * (1225.33 - x * (3574.96 - x * (1073.77 + x * 707.56))));
  const b = 27.2 + x * (3211.1 - x * (15327.97 - x * (27814 - x * (22569.18 - x * 6838.66))));
  const c = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
  return `rgb(${c(r)},${c(g)},${c(b)})`;
}
