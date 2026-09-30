export function fmtTime(s: number | null | undefined, decimals = 1): string {
  if (s === null || s === undefined || !isFinite(s)) return "--";
  const neg = s < 0;
  s = Math.abs(s);
  const m = Math.floor(s / 60);
  const sec = s - m * 60;
  const ss = sec.toFixed(decimals).padStart(decimals ? 3 + decimals : 2, "0");
  return `${neg ? "-" : ""}${m}:${ss}`;
}

export function fmtDelta(s: number | null | undefined): string {
  if (s === null || s === undefined) return "--";
  return (s > 0 ? "+" : s < 0 ? "-" : "") + fmtTime(Math.abs(s));
}

export function fmtM(m: number | null | undefined, d = 0): string {
  if (m === null || m === undefined || !isFinite(m)) return "--";
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${m.toFixed(d)} m`;
}

export function fmtNum(v: number | null | undefined, d = 0): string {
  if (v === null || v === undefined || !isFinite(v)) return "--";
  return v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
}

export function fmtClock(epoch: number | null | undefined): string {
  if (!epoch) return "--";
  return new Date(epoch * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function fmtAgo(epoch: number | null | undefined): string {
  if (!epoch) return "--";
  const s = Date.now() / 1000 - epoch;
  if (s < 60) return `${Math.round(s)} s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  return `${(s / 3600).toFixed(1)} h ago`;
}

export const MODE_LABEL: Record<string, string> = {
  gps: "GPS",
  fused: "GPS + steps",
  dead_reckoning: "Dead reckoning",
};

export const SOURCE_LABEL: Record<string, string> = {
  gps: "measured by GPS",
  fused: "GPS fused with steps and heading",
  reconstructed: "reconstructed from steps and heading",
  straight: "no usable steps; straight line",
};

export const CATEGORY_FORMAT: Record<string, (v: number) => string> = {
  fastest: (v) => fmtTime(v),
  efficient: (v) => `${(v * 100).toFixed(0)}%`,
  crew: (v) => fmtDelta(v),
  steady: (v) => `${(v * 1000).toFixed(1)} mg`,
  steps: (v) => fmtNum(v),
  cadence: (v) => `${v.toFixed(0)} spm`,
  speed: (v) => `${v.toFixed(2)} m/s`,
};
