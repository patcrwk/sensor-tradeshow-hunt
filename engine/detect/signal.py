"""Small signal helpers shared by the detectors."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import signal


def uniform(df: pd.DataFrame, cols: list[str], fs: float | None = None) -> tuple[np.ndarray, np.ndarray, float]:
    """Resample columns of df onto a uniform time grid. Returns (t, X[n, k], fs)."""
    t = df["t"].to_numpy()
    if fs is None:
        fs = estimate_rate(t)
    if len(t) < 2:
        return t, df[cols].to_numpy(dtype=np.float64), fs
    tu = np.arange(t[0], t[-1], 1.0 / fs)
    X = np.column_stack([np.interp(tu, t, df[c].to_numpy(dtype=np.float64)) for c in cols])
    return tu, X, fs


def estimate_rate(t: np.ndarray) -> float:
    if len(t) < 2:
        return 1.0
    d = np.diff(t)
    d = d[d > 0]
    return float(1.0 / np.median(d)) if len(d) else 1.0


def butter(x: np.ndarray, fs: float, low: float | None = None, high: float | None = None,
           order: int = 3) -> np.ndarray:
    """Zero-phase Butterworth. low = highpass cutoff, high = lowpass cutoff."""
    nyq = fs / 2.0
    if high is not None and high >= nyq * 0.98:
        high = None
    if low is not None and high is not None:
        sos = signal.butter(order, [low / nyq, high / nyq], btype="bandpass", output="sos")
    elif low is not None:
        sos = signal.butter(order, low / nyq, btype="highpass", output="sos")
    elif high is not None:
        sos = signal.butter(order, high / nyq, btype="lowpass", output="sos")
    else:
        return x
    if x.shape[0] <= 3 * (2 * order + 1):
        return x
    return signal.sosfiltfilt(sos, x, axis=0)


def rolling(x: np.ndarray, n: int, fn: str = "mean") -> np.ndarray:
    s = pd.Series(x)
    r = s.rolling(max(n, 1), center=True, min_periods=1)
    return getattr(r, fn)().to_numpy()


def segments(mask: np.ndarray) -> list[tuple[int, int]]:
    """Return [start, end) index pairs of True runs."""
    if not len(mask):
        return []
    m = np.concatenate([[False], mask.astype(bool), [False]])
    d = np.diff(m.astype(np.int8))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0]
    return list(zip(starts.tolist(), ends.tolist()))


def interp_to(t_src: np.ndarray, x_src: np.ndarray, t_dst: np.ndarray) -> np.ndarray:
    if x_src.ndim == 1:
        return np.interp(t_dst, t_src, x_src)
    return np.column_stack([np.interp(t_dst, t_src, x_src[:, i]) for i in range(x_src.shape[1])])


def minmax_downsample(t: np.ndarray, y: np.ndarray, n_bins: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bin into n_bins; return (t_center, ymin, ymax). Keeps peaks visible."""
    if len(t) <= n_bins * 2:
        return t, y, y
    edges = np.linspace(0, len(t), n_bins + 1).astype(int)
    idx = edges[:-1]
    ymin = np.minimum.reduceat(y, idx)
    ymax = np.maximum.reduceat(y, idx)
    tc = t[np.minimum((edges[:-1] + edges[1:]) // 2, len(t) - 1)]
    return tc, ymin, ymax
