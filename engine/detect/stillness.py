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
    reason: str                 # "surface", "off_band", "hand_held", "too_short"

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


def detect_rests(b: Bundle, cfg=None, min_rest_s: float | None = None,
                 mag_band_g: float | None = None) -> StillnessResult:
    cfg = cfg or get_config()
    c = cfg.stillness
    band = c.mag_band_g if mag_band_g is None else mag_band_g
    acc = b.role("accel")
    if acc is None or len(acc) < 10:
        return StillnessResult([], [], np.array([]), np.array([]), np.array([]), 0.0)
    t, A, fs = uniform(acc, ["x", "y", "z"])
    mag = np.linalg.norm(A, axis=1)
    n = int(round(c.window_s * fs))
    mmean = rolling(mag, n, "mean")
    mstd = rolling(mag, n, "std")
    still = (np.abs(mmean - 1.0) < band) & (mstd < c.accel_std_g)

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
    # A bump on the table (a nudge, someone touching the phone next to it) splits one
    # rest into pieces a second or two apart. If the sensor lies in the same pose
    # before and after, it never left the surface: join the pieces.
    joined: list[list[int]] = []
    settle = int(c.settle_gap_s * fs)
    for s, e in merged:
        if joined and s - joined[-1][1] <= settle:
            ga = A[joined[-1][0]:joined[-1][1]].mean(axis=0)
            gb = A[s:e].mean(axis=0)
            cos = float(np.dot(ga, gb) / (np.linalg.norm(ga) * np.linalg.norm(gb) or 1.0))
            if np.degrees(np.arccos(np.clip(cos, -1, 1))) <= c.settle_max_deg:
                joined[-1][1] = e
                continue
        joined.append([s, e])
    merged = joined

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
        tr = _tremor(trem[ss:ee], fs) if trem is not None else 0.0
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


def _tremor(x: np.ndarray, fs: float) -> float:
    """Tremor-band RMS, as the median over 1 s windows: a hand shakes the whole
    time, while a single bump on the table only spoils one window."""
    p = np.sum(x ** 2, axis=1)
    w = max(int(fs), 1)
    n = len(p) // w
    if n < 3:
        return float(np.sqrt(np.mean(p))) if len(p) else 0.0
    return float(np.sqrt(np.median(p[: n * w].reshape(n, w).mean(axis=1))))

