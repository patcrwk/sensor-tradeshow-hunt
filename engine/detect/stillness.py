"""Detect 10-second rests on a surface from DC acceleration and rotation.

A rest is a stretch where |accel| stays near 1 g with low variance and the
rotation rate stays near zero. Hand-held pauses pass those tests more often
than you would expect, so each candidate is also checked for energy in the
physiological tremor band (about 4 to 12 Hz); too much means "in a hand".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from ..config import get_config
from ..io.bundle import Bundle
from .signal import butter, interp_to, rolling, segments, uniform


@dataclass
class Rest:
    start: float
    end: float
    duration: float
    gravity: list[float]        # mean accel vector during the rest (g)
    gravity_unit: list[float]
    accel_std_g: float
    gyro_mean_dps: float | None
    tremor_rms_g: float
    accepted: bool
    reason: str                 # "surface", "hand_held", "too_short"

    @property
    def mid(self) -> float:
        return (self.start + self.end) / 2

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mid"] = self.mid
        d["source"] = {
            "channels": ["accel", "gyro"],
            "method": "stillness: |a| within band of 1 g, low std, low rotation; tremor band check",
            "window": [round(self.start, 2), round(self.end, 2)],
        }
        return d


@dataclass
class StillnessResult:
    rests: list[Rest]           # accepted rests
    rejected: list[Rest]        # candidates rejected (hand-held, too short)
    trace_t: np.ndarray         # downsampled stillness trace for the UI
    trace_std: np.ndarray
    trace_still: np.ndarray
    fs: float


def detect_rests(b: Bundle, cfg=None, min_rest_s: float | None = None) -> StillnessResult:
    cfg = cfg or get_config()
    c = cfg.stillness
    acc = b.role("accel")
    if acc is None or len(acc) < 10:
        return StillnessResult([], [], np.array([]), np.array([]), np.array([]), 0.0)
    t, A, fs = uniform(acc, ["x", "y", "z"])
    mag = np.linalg.norm(A, axis=1)
    n = int(round(c.window_s * fs))
    mmean = rolling(mag, n, "mean")
    mstd = rolling(mag, n, "std")
    still = (np.abs(mmean - 1.0) < c.mag_band_g) & (mstd < c.accel_std_g)

    gyro = b.role("gyro")
    gmag = None
    if gyro is not None and len(gyro) > 2:
        gt = gyro["t"].to_numpy()
        gm = np.linalg.norm(gyro[["x", "y", "z"]].to_numpy(dtype=np.float64), axis=1)
        gmag = interp_to(gt, gm, t)
        gmag = rolling(gmag, n, "mean")
        still &= gmag < c.gyro_max_dps

    # Merge short blips
    segs = segments(still)
    merged: list[list[int]] = []
    gap = int(c.merge_gap_s * fs)
    for s, e in segs:
        if merged and s - merged[-1][1] <= gap:
            merged[-1][1] = e
        else:
            merged.append([s, e])

    lo, hi = c.tremor_band_hz
    trem = butter(A, fs, low=lo, high=hi) if fs > 2.2 * hi else None
    min_len = c.min_rest_s if min_rest_s is None else min_rest_s

    rests, rejected = [], []
    for s, e in merged:
        dur = (e - s) / fs
        if dur < min(2.0, min_len):
            continue
        # Trim half a window at each edge; rolling stats bleed into motion.
        pad = min(n // 2, (e - s) // 4)
        ss, ee = s + pad, e - pad
        g = A[ss:ee].mean(axis=0)
        gn = g / (np.linalg.norm(g) or 1.0)
        tr = float(np.sqrt(np.mean(np.sum(trem[ss:ee] ** 2, axis=1)))) if trem is not None else 0.0
        r = Rest(
            start=float(t[s]), end=float(t[e - 1]), duration=float(dur),
            gravity=[round(float(v), 5) for v in g], gravity_unit=[round(float(v), 5) for v in gn],
            accel_std_g=float(np.std(mag[ss:ee])),
            gyro_mean_dps=float(np.mean(gmag[ss:ee])) if gmag is not None else None,
            tremor_rms_g=tr, accepted=True, reason="surface",
        )
        if tr > c.tremor_rms_max_g:
            r.accepted, r.reason = False, "hand_held"
            rejected.append(r)
        elif dur < min_len:
            r.accepted, r.reason = False, "too_short"
            if dur >= 3.0:
                rejected.append(r)
        else:
            rests.append(r)

    # Downsampled trace for plots (about 2 points per second)
    step = max(int(fs / 2), 1)
    return StillnessResult(rests, rejected, t[::step], mstd[::step], still[::step].astype(np.int8), fs)
