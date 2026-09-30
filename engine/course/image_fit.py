"""Georeference a background image by pinning stations.

Pins map course local coordinates (x, y meters) to image pixels (u, v).
Two pins: similarity transform (scale, rotation, translation).
Three or more: least-squares affine.
The transform is stored as a 2x3 matrix M so that [u, v] = M @ [x, y, 1].
"""
from __future__ import annotations

import numpy as np


def fit(pins: list[dict], kind: str | None = None) -> dict:
    """pins: [{x, y, u, v}]. Returns {kind, matrix, rms_px}."""
    if len(pins) < 2:
        raise ValueError("need at least two pins")
    P = np.array([[p["x"], p["y"]] for p in pins], float)
    Q = np.array([[p["u"], p["v"]] for p in pins], float)
    kind = kind or ("affine" if len(pins) >= 3 else "similarity")
    if kind == "affine" and len(pins) >= 3:
        A = np.column_stack([P, np.ones(len(P))])
        sol, *_ = np.linalg.lstsq(A, Q, rcond=None)
        M = sol.T
    else:
        # Similarity via complex least squares: q = a * p + b
        pc = P[:, 0] + 1j * P[:, 1]
        qc = Q[:, 0] + 1j * Q[:, 1]
        A = np.column_stack([pc, np.ones(len(pc))])
        (a, b), *_ = np.linalg.lstsq(A, qc, rcond=None)
        M = np.array([[a.real, -a.imag, b.real], [a.imag, a.real, b.imag]])
        kind = "similarity"
    pred = (M @ np.column_stack([P, np.ones(len(P))]).T).T
    rms = float(np.sqrt(np.mean(np.sum((pred - Q) ** 2, axis=1))))
    return {"kind": kind, "matrix": M.round(8).tolist(), "rms_px": round(rms, 2)}


def apply(M, x, y):
    M = np.asarray(M, float)
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    return M[0, 0] * x + M[0, 1] * y + M[0, 2], M[1, 0] * x + M[1, 1] * y + M[1, 2]
