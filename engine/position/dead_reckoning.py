"""Step detection and pedestrian dead reckoning.

Heading convention everywhere: theta is the math angle in radians,
counter-clockwise from +x (east). A step moves (L cos theta, L sin theta).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from ..config import get_config
from ..detect.signal import butter, interp_to, uniform
from ..io.bundle import Bundle


@dataclass
class Steps:
    t: np.ndarray               # step timestamps
    heading: np.ndarray         # relative heading at each step (rad, arbitrary zero)
    count: int
    cadence_spm: float          # median cadence while walking
    walking_s: float            # time spent walking

    def to_dict(self) -> dict:
        return {"count": self.count, "cadence_spm": round(self.cadence_spm, 1),
                "walking_s": round(self.walking_s, 1),
                "source": {"channels": ["accel", "gyro"],
                           "method": "band-passed |accel| peaks; yaw = gyro projected on gravity"}}


def yaw_heading(b: Bundle, cfg=None, walking=None) -> tuple[np.ndarray, np.ndarray] | None:
    """Integrated heading (rad) on the gyro timebase, using gravity from accel."""
    cfg = cfg or get_config()
    gyro = b.role("gyro")
    acc = b.role("accel")
    if gyro is None or acc is None or len(gyro) < 10:
        return None
    tg, G, fsg = uniform(gyro, ["x", "y", "z"])
    ta, A, fsa = uniform(acc, ["x", "y", "z"])
    grav = butter(A, fsa, high=cfg.stillness.gravity_lowpass_hz)
    grav = interp_to(ta, grav, tg)
    up = grav / np.maximum(np.linalg.norm(grav, axis=1, keepdims=True), 1e-6)
    # Remove the 3-axis gyro bias, estimated while the sensor is still. It must be
    # removed per axis before projecting, since "up" differs between poses.
    quiet = np.linalg.norm(G, axis=1) < cfg.stillness.gyro_max_dps
    if quiet.sum() > fsg:
        G = G - np.median(G[quiet], axis=0)
    wz = np.radians(np.sum(G * up, axis=1))           # yaw rate about "up"
    if walking is not None:
        # Heading only changes while walking. Pick-up and put-down tilt the
        # sensor, and the lagging gravity estimate would leak that into yaw.
        wz = np.where(walking(tg), wz, 0.0)
    theta = np.concatenate([[0.0], np.cumsum(0.5 * (wz[1:] + wz[:-1]) * np.diff(tg))])
    return tg, theta


def detect_steps(b: Bundle, cfg=None, exclude: list[tuple[float, float]] | None = None) -> Steps:
    cfg = cfg or get_config()
    c = cfg.steps
    acc = b.role("accel")
    if acc is None or len(acc) < 50:
        return Steps(np.array([]), np.array([]), 0, 0.0, 0.0)
    t, A, fs = uniform(acc, ["x", "y", "z"])
    mag = np.linalg.norm(A, axis=1)
    bp = butter(mag - mag.mean(), fs, low=c.band_hz[0], high=c.band_hz[1])
    pk, _ = find_peaks(bp, height=c.min_peak_g, distance=max(int(c.min_spacing_s * fs), 1))
    ts = t[pk]
    if exclude:
        keep = np.ones(len(ts), bool)
        for s, e in exclude:
            keep &= ~((ts >= s) & (ts <= e))
        ts = ts[keep]
    # Isolated peaks are not walking: require a neighbour within 1.2 s
    if len(ts) > 2:
        d = np.diff(ts)
        near = np.zeros(len(ts), bool)
        near[:-1] |= d < 1.2
        near[1:] |= d < 1.2
        ts = ts[near]
    hd = yaw_heading(b, cfg, walking=_walking_fn(ts))
    heading = np.interp(ts, hd[0], hd[1]) if hd is not None else np.zeros(len(ts))
    d = np.diff(ts)
    walk = d[d < 1.2]
    cadence = float(60.0 / np.median(walk)) if len(walk) else 0.0
    return Steps(ts, heading, len(ts), cadence, float(walk.sum()))


def _walking_fn(step_t: np.ndarray, pad: float = 0.6):
    """Return f(t) -> bool mask of times within a run of steps."""
    if len(step_t) < 2:
        return None
    d = np.diff(step_t)
    runs = [(a - pad, b + pad) for a, b, dd in zip(step_t[:-1], step_t[1:], d) if dd < 1.2]

    def f(t):
        m = np.zeros(len(t), bool)
        for a, b in runs:
            i0, i1 = np.searchsorted(t, [a, b])
            m[i0:i1] = True
        return m
    return f


def dr_path(steps: Steps, step_length: float, t0: float = 0.0, t_end: float | None = None,
            theta0: float = 0.0) -> pd.DataFrame:
    """Integrate steps into a raw 2D path starting at (0, 0)."""
    th = steps.heading + theta0
    dx = step_length * np.cos(th)
    dy = step_length * np.sin(th)
    x = np.concatenate([[0.0], np.cumsum(dx)])
    y = np.concatenate([[0.0], np.cumsum(dy)])
    t = np.concatenate([[t0], steps.t])
    if t_end is not None and (not len(steps.t) or t_end > steps.t[-1]):
        t = np.append(t, t_end)
        x = np.append(x, x[-1])
        y = np.append(y, y[-1])
    return pd.DataFrame({"t": t, "x": x, "y": y})


def position_at(path: pd.DataFrame, t: float) -> tuple[float, float]:
    return float(np.interp(t, path["t"], path["x"])), float(np.interp(t, path["t"], path["y"]))


def anchor_legs(path: pd.DataFrame, anchors: list[dict], cfg=None) -> tuple[pd.DataFrame, list[dict]]:
    """Fit each leg between known positions with a similarity transform.

    anchors: [{t_start, t_end, x, y}] rests with known course positions, in time order.
    Returns (points with columns t, x, y, source, leg) and per-leg notes.
    """
    cfg = cfg or get_config()
    dr = cfg.dead_reckoning
    out, notes = [], []
    for i in range(len(anchors) - 1):
        a, b = anchors[i], anchors[i + 1]
        ta, tb = a["t_end"], b["t_start"]
        seg = path[(path["t"] >= ta) & (path["t"] <= tb)]
        pa, pb = np.array([a["x"], a["y"]]), np.array([b["x"], b["y"]])
        n_steps = len(seg)
        ra, rb = np.array(position_at(path, ta)), np.array(position_at(path, tb))
        dv, target = rb - ra, pb - pa
        ok = n_steps >= dr.min_leg_steps and np.linalg.norm(dv) > 0.5
        scale = np.linalg.norm(target) / np.linalg.norm(dv) if ok else 0
        if ok and not (dr.min_scale <= scale <= dr.max_scale) and np.linalg.norm(target) > 3:
            ok = False
        if ok:
            rot = np.arctan2(target[1], target[0]) - np.arctan2(dv[1], dv[0])
            c, s = np.cos(rot) * scale, np.sin(rot) * scale
            P = np.column_stack([seg["x"], seg["y"]]) - ra
            Q = np.column_stack([c * P[:, 0] - s * P[:, 1], s * P[:, 0] + c * P[:, 1]]) + pa
            pts = np.vstack([pa, Q, pb])
            ts = np.concatenate([[ta], seg["t"].to_numpy(), [tb]])
            src = "reconstructed"
            notes.append({"leg": i, "steps": n_steps, "scale": round(float(scale), 2),
                          "rotation_deg": round(float(np.degrees(rot)), 1), "fallback": False})
        else:
            pts = np.vstack([pa, pb])
            ts = np.array([ta, tb])
            src = "straight"
            notes.append({"leg": i, "steps": n_steps, "fallback": True,
                          "reason": "too few steps" if n_steps < dr.min_leg_steps else "failed sanity check"})
        # hold position during the rest at a
        out.append(pd.DataFrame({"t": [a["t_start"]], "x": [pa[0]], "y": [pa[1]], "source": [src], "leg": [i]}))
        out.append(pd.DataFrame({"t": ts, "x": pts[:, 0], "y": pts[:, 1], "source": src, "leg": i}))
    if anchors:
        last = anchors[-1]
        out.append(pd.DataFrame({"t": [last["t_start"], last["t_end"]], "x": [last["x"]] * 2,
                                 "y": [last["y"]] * 2, "source": "reconstructed", "leg": len(anchors) - 1}))
    if not out:
        return pd.DataFrame(columns=["t", "x", "y", "source", "leg"]), notes
    return pd.concat(out, ignore_index=True), notes
