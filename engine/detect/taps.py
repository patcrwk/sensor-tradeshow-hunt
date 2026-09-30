"""Detect tap groups (short acceleration spikes) and label the rest that follows."""
from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from ..config import get_config
from ..io.bundle import Bundle
from .signal import butter, uniform


def detect_taps(b: Bundle, cfg=None) -> list[float]:
    """Return tap timestamps (seconds)."""
    cfg = cfg or get_config()
    c = cfg.taps
    acc = b.role("accel")
    if acc is None or len(acc) < 10:
        return []
    t, A, fs = uniform(acc, ["x", "y", "z"])
    hp = butter(A, fs, low=c.highpass_hz)
    mag = np.linalg.norm(hp, axis=1)
    peaks, _ = find_peaks(mag, height=c.threshold_g, distance=max(int(c.min_spacing_s * fs), 1))
    return t[peaks].tolist()


def group_taps(taps: list[float], cfg=None) -> list[dict]:
    cfg = cfg or get_config()
    c = cfg.taps
    groups: list[list[float]] = []
    for tp in taps:
        if groups and c.min_spacing_s * 0.9 <= tp - groups[-1][-1] <= c.max_spacing_s:
            groups[-1].append(tp)
        else:
            groups.append([tp])
    return [{"start": g[0], "end": g[-1], "count": len(g), "times": g} for g in groups]


def label_rest(rest_start: float, groups: list[dict], cfg=None) -> dict:
    """Find the tap group that ends just before the rest."""
    cfg = cfg or get_config()
    best = None
    for g in groups:
        gap = rest_start - g["end"]
        if -0.5 <= gap <= cfg.taps.max_gap_before_rest_s:
            best = g
    if best is None:
        return {"method": "taps", "count": None, "detail": "no tap group before rest"}
    return {"method": "taps", "count": best["count"], "tap_times": best["times"],
            "detail": f"{best['count']} taps ending {rest_start - best['end']:.1f} s before rest"}
