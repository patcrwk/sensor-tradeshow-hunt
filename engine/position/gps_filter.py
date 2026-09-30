"""Quality-filter and smooth a GPS track, and estimate per-fix accuracy."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import get_config
from .projection import LocalFrame


def fix_sigma(gps: pd.DataFrame, cfg=None) -> np.ndarray:
    """Best available 1-sigma horizontal accuracy estimate per fix (meters)."""
    cfg = cfg or get_config()
    n = len(gps)
    if "acc" in gps:
        s = gps["acc"].to_numpy(dtype=float)
    elif "hdop" in gps:
        s = gps["hdop"].to_numpy(dtype=float) * 2.5   # UERE of about 2.5 m
    else:
        s = np.full(n, cfg.fusion.default_gps_sigma_m)
    s = np.where(np.isfinite(s) & (s > 0), s, cfg.fusion.default_gps_sigma_m)
    return np.maximum(s, 0.5)


def valid_mask(gps: pd.DataFrame, cfg=None) -> np.ndarray:
    """Fixes that pass the quality thresholds (before jump rejection)."""
    cfg = cfg or get_config()
    g = cfg.gps
    ok = np.isfinite(gps["lat"].to_numpy()) & np.isfinite(gps["lon"].to_numpy())
    if "fix" in gps:
        ok &= gps["fix"].fillna(0).to_numpy() > 0
    if "hdop" in gps:
        h = gps["hdop"].to_numpy(dtype=float)
        ok &= ~(np.isfinite(h) & (h > g.hdop_max))
    if "acc" in gps:
        a = gps["acc"].to_numpy(dtype=float)
        ok &= ~(np.isfinite(a) & (a > g.accuracy_max_m))
    if "sats" in gps:
        s = gps["sats"].to_numpy(dtype=float)
        ok &= ~(np.isfinite(s) & (s < g.sats_min))
    return ok


def filtered_track(gps: pd.DataFrame, frame: LocalFrame, cfg=None, smooth: bool = True) -> pd.DataFrame:
    """Return DataFrame t, x, y, sigma of accepted, smoothed fixes in the local frame."""
    cfg = cfg or get_config()
    if gps is None or not len(gps):
        return pd.DataFrame(columns=["t", "x", "y", "sigma"])
    ok = valid_mask(gps, cfg)
    g = gps[ok]
    x, y = frame.to_xy(g["lat"].to_numpy(), g["lon"].to_numpy())
    t = g["t"].to_numpy()
    sig = fix_sigma(g, cfg)
    keep = _reject_jumps(t, x, y, sig, cfg.gps.max_walk_speed_mps)
    df = pd.DataFrame({"t": t[keep], "x": x[keep], "y": y[keep], "sigma": sig[keep]})
    if smooth and len(df) > 3:
        df = smooth_track(df, cfg.gps.smooth_window_s)
    return df.reset_index(drop=True)


def _reject_jumps(t, x, y, sig, vmax) -> np.ndarray:
    keep = np.ones(len(t), bool)
    last = None
    for i in range(len(t)):
        if last is None:
            last = i
            continue
        dt = max(t[i] - t[last], 1e-3)
        d = np.hypot(x[i] - x[last], y[i] - y[last])
        # Allow the jump if it fits inside the combined error budget
        if d > vmax * dt + 2 * (sig[i] + sig[last]):
            keep[i] = False
        else:
            last = i
    return keep


def smooth_track(df: pd.DataFrame, window_s: float) -> pd.DataFrame:
    """Accuracy-weighted moving average over a time window."""
    t = df["t"].to_numpy()
    w = 1.0 / df["sigma"].to_numpy() ** 2
    x = df["x"].to_numpy()
    y = df["y"].to_numpy()
    xs, ys = np.empty_like(x), np.empty_like(y)
    j0 = j1 = 0
    h = window_s / 2
    for i in range(len(t)):
        while t[j0] < t[i] - h:
            j0 += 1
        while j1 < len(t) and t[j1] <= t[i] + h:
            j1 += 1
        ww = w[j0:j1]
        xs[i] = np.sum(x[j0:j1] * ww) / ww.sum()
        ys[i] = np.sum(y[j0:j1] * ww) / ww.sum()
    out = df.copy()
    out["x"], out["y"] = xs, ys
    return out


def average_fix(gps: pd.DataFrame, start: float, end: float, cfg=None) -> dict | None:
    """Quality-weighted mean lat/lon over a window, plus spread and sigma of the mean."""
    cfg = cfg or get_config()
    if gps is None or not len(gps):
        return None
    seg = gps[(gps["t"] >= start) & (gps["t"] <= end)]
    if not len(seg):
        return None
    seg = seg[valid_mask(seg, cfg)]
    if not len(seg):
        return None
    sig = fix_sigma(seg, cfg)
    w = 1.0 / sig ** 2
    lat = float(np.sum(seg["lat"].to_numpy() * w) / w.sum())
    lon = float(np.sum(seg["lon"].to_numpy() * w) / w.sum())
    fr = LocalFrame(lat, lon)
    x, y = fr.to_xy(seg["lat"].to_numpy(), seg["lon"].to_numpy())
    spread = float(np.sqrt(np.mean(x ** 2 + y ** 2)))
    return {
        "lat": lat, "lon": lon, "n": int(len(seg)), "spread_m": spread,
        "sigma_m": float(np.median(sig)),
        # 95% horizontal radius. The error of a time-averaged fix is dominated
        # by slow, correlated drift, so it is not divided by sqrt(n). Reported
        # accuracy (about a 68% radius) times 1.7 approximates 95%.
        "accuracy_m": float(max(2.0 * spread, 1.7 * np.median(sig))),
    }


def availability(gps: pd.DataFrame | None, t0: float, t1: float, cfg=None) -> float:
    """Fraction of seconds in [t0, t1] with at least one accepted fix."""
    if gps is None or not len(gps) or t1 <= t0:
        return 0.0
    ok = valid_mask(gps, cfg)
    t = gps["t"].to_numpy()[ok]
    t = t[(t >= t0) & (t <= t1)]
    secs = np.unique(np.floor(t - t0))
    return float(min(len(secs) / max(np.ceil(t1 - t0), 1), 1.0))
