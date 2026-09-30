"""GPS + step/heading fusion with a small extended Kalman filter.

State: [x, y, heading_offset, step_scale]. Each detected step predicts a move
of step_scale * L along (gyro heading + heading_offset). Each accepted GPS fix
pulls x, y back. The filter learns the gyro-to-map heading offset and the
participant's step length as it goes, so it can coast through dropouts.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import get_config
from .dead_reckoning import Steps


def fuse(steps: Steps, gps_xy: pd.DataFrame, step_length: float, cfg=None,
         start_xy: tuple[float, float] | None = None, t0: float | None = None,
         t_end: float | None = None) -> pd.DataFrame:
    cfg = cfg or get_config()
    f = cfg.fusion
    ev = [(float(t), 0, i) for i, t in enumerate(steps.t)]
    ev += [(float(t), 1, i) for i, t in enumerate(gps_xy["t"].to_numpy())] if len(gps_xy) else []
    ev.sort()

    gx, gy, gs = (gps_xy[c].to_numpy() if len(gps_xy) else np.array([]) for c in ("x", "y", "sigma"))
    gt = gps_xy["t"].to_numpy() if len(gps_xy) else np.array([])

    # Initial position
    if start_xy is not None:
        x0, y0 = start_xy
    elif len(gx):
        x0, y0 = gx[0], gy[0]
    else:
        x0, y0 = 0.0, 0.0
    off = _initial_offset(steps, gt, gx, gy, step_length)
    X = np.array([x0, y0, off, 1.0])
    P = np.diag([4.0 if start_xy else 25.0] * 2 + [np.radians(30) ** 2, 0.05])
    Qxy = f.step_noise_m ** 2
    Qh = np.radians(1.0) ** 2
    Qs = 1e-5

    rows = [(t0 if t0 is not None else (ev[0][0] if ev else 0.0), X[0], X[1], "fused")]
    for t, kind, i in ev:
        if kind == 0:
            th = steps.heading[i] + X[2]
            L = step_length * X[3]
            c, s = np.cos(th), np.sin(th)
            X[0] += L * c
            X[1] += L * s
            F = np.eye(4)
            F[0, 2], F[1, 2] = -L * s, L * c
            F[0, 3], F[1, 3] = step_length * c, step_length * s
            P = F @ P @ F.T + np.diag([Qxy, Qxy, Qh, Qs])
        else:
            z = np.array([gx[i], gy[i]])
            R = np.eye(2) * gs[i] ** 2
            H = np.zeros((2, 4))
            H[0, 0] = H[1, 1] = 1.0
            y = z - X[:2]
            S = H @ P @ H.T + R
            # Gate outliers (chi-square 2 dof, 99.9%)
            if float(y @ np.linalg.solve(S, y)) > 13.8 and len(rows) > 5:
                P[:2, :2] += np.eye(2) * f.process_noise
                continue
            K = P @ H.T @ np.linalg.inv(S)
            X = X + K @ y
            X[3] = float(np.clip(X[3], 0.6, 1.5))
            P = (np.eye(4) - K @ H) @ P
        rows.append((t, X[0], X[1], "fused"))
    if t_end is not None and rows and t_end > rows[-1][0]:
        rows.append((t_end, X[0], X[1], "fused"))
    return pd.DataFrame(rows, columns=["t", "x", "y", "source"])


def _initial_offset(steps: Steps, gt, gx, gy, L) -> float:
    """Align gyro heading with GPS course over the first stretch of walking."""
    if len(steps.t) < 10 or len(gt) < 5:
        return 0.0
    best = 0.0
    n = min(len(steps.t), 40)
    ta, tb = steps.t[0], steps.t[n - 1]
    ia, ib = np.searchsorted(gt, ta), np.searchsorted(gt, tb)
    if ib - ia < 3 or ib >= len(gt):
        return best
    gdx, gdy = gx[ib] - gx[ia], gy[ib] - gy[ia]
    if np.hypot(gdx, gdy) < 5:
        return best
    th = steps.heading[:n]
    ddx, ddy = np.sum(np.cos(th)) * L, np.sum(np.sin(th)) * L
    return float(np.arctan2(gdy, gdx) - np.arctan2(ddy, ddx))
