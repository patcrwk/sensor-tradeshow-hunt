"""Run metrics and the "how the sensor saw it" traces."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import get_config
from ..detect.signal import butter, minmax_downsample, uniform
from ..io.bundle import Bundle
from ..position.gps_filter import fix_sigma, valid_mask
from ..position.projection import path_length


def run_metrics(b: Bundle, route: pd.DataFrame, steps, t0: float, t1: float, cfg=None) -> dict:
    cfg = cfg or get_config()
    out: dict = {}
    dist = path_length(route["x"], route["y"]) if len(route) else 0.0
    out["distance_m"] = round(dist, 1)
    out["distance_source"] = {"method": f"length of {', '.join(sorted(set(route['source']))) if len(route) else 'no'} route",
                              "window": [round(t0, 1), round(t1, 1)]}
    sel = (steps.t >= t0) & (steps.t <= t1)
    out["steps"] = int(sel.sum())
    out["cadence_spm"] = round(steps.cadence_spm, 1)
    dur = max(t1 - t0, 1e-3)
    out["avg_speed_mps"] = round(dist / dur, 2)

    acc = b.role("accel")
    if acc is not None and len(acc) > 10:
        seg = acc[(acc["t"] >= t0) & (acc["t"] <= t1)]
        if len(seg) > 10:
            t, A, fs = uniform(seg, ["x", "y", "z"])
            mag = np.linalg.norm(A, axis=1)
            i = int(np.argmax(mag))
            out["peak_g"] = round(float(mag[i]), 2)
            out["peak_g_t"] = round(float(t[i]), 2)
            lo, hi = cfg.scoring.vibration_band_hz
            vib = butter(A, fs, low=lo, high=min(hi, fs * 0.45))
            vmag = np.linalg.norm(vib, axis=1)
            walking = _walking_mask(t, steps.t)
            if walking.sum() > fs * 5:
                out["vibration_rms_g"] = round(float(np.sqrt(np.mean(vmag[walking] ** 2))), 4)
                out["vibration_source"] = {"channel": "accel", "method": f"RMS of {lo:.0f} to {min(hi, fs * 0.45):.0f} Hz band while walking"}

    # Top walking speed: GPS speed if available, else from route
    speed = None
    if b.has_gps:
        g = b.gps()
        g = g[(g["t"] >= t0) & (g["t"] <= t1)]
        g = g[valid_mask(g, cfg)]
        if "speed" in g and len(g) > 5:
            s = g["speed"].rolling(5, center=True, min_periods=3).median()
            speed = float(np.nanmax(s)) if len(s) else None
            out["top_speed_source"] = {"channel": "gps", "method": "5-fix rolling median of GPS speed"}
    if speed is None and len(route) > 10:
        r = route.copy()
        d = np.hypot(np.diff(r["x"]), np.diff(r["y"]))
        dt = np.diff(r["t"])
        v = pd.Series(np.where(dt > 0, d / np.maximum(dt, 1e-3), 0)).rolling(9, center=True, min_periods=3).median()
        speed = float(np.nanmax(v)) if len(v) else None
        out["top_speed_source"] = {"method": "route derivative, rolling median"}
    if speed is not None:
        out["top_speed_mps"] = round(min(speed, 4.0), 2)

    env = b.role("env")
    if env is not None and len(env):
        e = env[(env["t"] >= t0) & (env["t"] <= t1)]
        if len(e):
            out["temperature_c"] = round(float(e["temperature"].mean()), 2) if "temperature" in e else None
            out["humidity_rh"] = round(float(e["humidity"].mean()), 1) if "humidity" in e else None
            out["floors"] = floor_changes(e, cfg)
    out["env_samples"] = env_samples(b, route, t0, t1)
    return out


def _walking_mask(t, step_t):
    m = np.zeros(len(t), bool)
    if len(step_t) < 2:
        return m
    d = np.diff(step_t)
    for a, bb, dd in zip(step_t[:-1], step_t[1:], d):
        if dd < 1.2:
            i0, i1 = np.searchsorted(t, [a, bb])
            m[i0:i1] = True
    return m


def floor_changes(env: pd.DataFrame, cfg=None) -> dict:
    cfg = cfg or get_config()
    f = cfg.floors
    p = env["pressure"].rolling(int(f.smooth_s * 10) or 1, center=True, min_periods=1).median()
    alt = (p.iloc[0] - p) / f.pa_per_m
    alt = alt.to_numpy()
    changes, level_ref = [], 0.0
    t = env["t"].to_numpy()
    for i in range(len(alt)):
        if abs(alt[i] - level_ref) >= f.level_change_m:
            changes.append({"t": round(float(t[i]), 1), "delta_m": round(float(alt[i] - level_ref), 1)})
            level_ref = alt[i]
    return {"max_height_m": round(float(np.max(alt)), 1), "min_height_m": round(float(np.min(alt)), 1),
            "changes": changes, "source": {"channel": "env.pressure", "method": f"{f.pa_per_m} Pa per meter"}}


def env_samples(b: Bundle, route: pd.DataFrame, t0: float, t1: float, every_s: float = 5.0) -> list[dict]:
    """Temperature, humidity and light tagged with position, for the crowd environment map."""
    if not len(route):
        return []
    ts = np.arange(t0, t1, every_s)
    x = np.interp(ts, route["t"], route["x"])
    y = np.interp(ts, route["t"], route["y"])
    out = {"t": ts, "x": x, "y": y}
    env = b.role("env")
    if env is not None and len(env):
        for c in ("temperature", "humidity"):
            if c in env:
                out[c] = np.interp(ts, env["t"], env[c])
    light = b.role("light")
    if light is not None and len(light) and "lux" in light:
        out["lux"] = np.interp(ts, light["t"], light["lux"])
    df = pd.DataFrame(out).round(2)
    return df.to_dict("records")


def sensor_view(b: Bundle, st, cfg=None, n: int = 600) -> dict:
    """Downsampled traces for the "how the sensor saw it" panel."""
    out: dict = {"stillness": {"t": np.round(st.trace_t, 1).tolist(),
                               "std_g": np.round(st.trace_std, 5).tolist(),
                               "still": st.trace_still.tolist()}}
    acc = b.role("accel")
    if acc is not None and len(acc):
        mag = np.linalg.norm(acc[["x", "y", "z"]].to_numpy(np.float64), axis=1)
        tc, lo, hi = minmax_downsample(acc["t"].to_numpy(), mag, n)
        out["accel_mag"] = {"t": np.round(tc, 2).tolist(), "min": np.round(lo, 3).tolist(), "max": np.round(hi, 3).tolist()}
    env = b.role("env")
    if env is not None and len(env):
        step = max(len(env) // n, 1)
        e = env.iloc[::step]
        out["env"] = {"t": e["t"].round(1).tolist(),
                      **{c: e[c].round(2).tolist() for c in ("pressure", "temperature", "humidity") if c in e}}
    light = b.role("light")
    if light is not None and len(light):
        step = max(len(light) // n, 1)
        li = light.iloc[::step]
        out["light"] = {"t": li["t"].round(1).tolist(), "lux": li["lux"].round(1).tolist()}
    if b.has_gps:
        g = b.gps()
        ok = valid_mask(g, cfg)
        out["gps"] = {"t": g["t"].round(1).tolist(), "sigma_m": np.round(fix_sigma(g, cfg), 1).tolist(),
                      "ok": ok.astype(int).tolist(),
                      "sats": g["sats"].tolist() if "sats" in g else None}
    return out
