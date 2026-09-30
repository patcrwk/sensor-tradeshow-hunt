"""Frequency tab: Welch PSD, spectrogram and octave bands via endaq.calc.psd."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import endaq.calc.psd as epsd
from scipy.signal import find_peaks

from ..io.bundle import Bundle


def accel_frame(b: Bundle, role: str) -> tuple[pd.DataFrame, dict] | None:
    ch = b.roles.get(role)
    if ch is None:
        return None
    df = b.channel(ch).set_index("t")[["x", "y", "z"]].astype("float64")
    df["resultant"] = np.linalg.norm(df[["x", "y", "z"]].to_numpy(), axis=1)
    return df, b.channel_info(ch)


def frequency(b: Bundle, role: str | None = None, fmin: float = 10.0, max_points: int = 800) -> dict:
    role = role or ("hf_accel" if b.roles.get("hf_accel") else "accel")
    got = accel_frame(b, role) or accel_frame(b, "accel")
    if got is None:
        return {"available": False}
    df, info = got
    fs = info.get("rate_hz") or 1.0
    bw = 1.0 if fs >= 400 else max(fs / 400, 0.1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        psd = epsd.welch(df, bin_width=bw)
        octv = epsd.to_octave(epsd.welch(df[["x", "y", "z"]], bin_width=bw), fstart=1.0, octave_bins=3)
    psd = psd[psd.index > 0]
    peaks = dominant_peaks(psd, fmin=fmin)
    return {
        "available": True,
        "channel": info["id"], "channel_name": info["name"], "rate_hz": fs,
        "units": "g²/Hz",
        "psd": _log_decimate(psd, max_points),
        "octave": {"f": [round(float(f), 2) for f in octv.index],
                   **{c: [float(v) for v in octv[c]] for c in octv.columns}},
        "spectrogram": spectrogram(df, fs),
        "peaks": peaks,
        "source": {"channel": info["name"], "method": f"Welch PSD (endaq.calc.psd.welch), {bw:g} Hz bins, "
                                                     "full recording; peaks above " + f"{fmin:g} Hz"},
    }


def dominant_peaks(psd: pd.DataFrame, fmin: float = 10.0, n: int = 5) -> list[dict]:
    p = psd[psd.index >= fmin]
    out = []
    for c in p.columns:
        y = p[c].to_numpy()
        idx, _ = find_peaks(y, distance=max(int(5 / max(np.diff(p.index[:2])[0], 1e-6)), 1))
        if not len(idx):
            continue
        top = idx[np.argsort(y[idx])[::-1][:n]]
        for rank, i in enumerate(top):
            out.append({"axis": c, "f_hz": round(float(p.index[i]), 1), "psd": float(y[i]), "rank": rank + 1})
    return out


def spectrogram(df: pd.DataFrame, fs: float, n_t: int = 160, n_f: int = 128, col: str = "resultant") -> dict:
    """Log-power spectrogram on a compact grid for a heat map."""
    from scipy.signal import spectrogram as sg
    x = df[col].to_numpy()
    x = x - np.median(x)
    nper = int(min(max(fs, 256), len(x) // 4 or 256))
    step = max((len(x) - nper) // n_t, nper // 4)
    f, t, S = sg(x, fs=fs, nperseg=nper, noverlap=max(nper - step, 0), scaling="density")
    fmax = min(fs / 2, 1000.0)
    sel = (f > 0) & (f <= fmax)
    f, S = f[sel], S[sel]
    # log-spaced frequency rows
    edges = np.logspace(np.log10(max(f[0], 1.0)), np.log10(f[-1]), n_f + 1)
    rows = []
    for a, bb in zip(edges[:-1], edges[1:]):
        m = (f >= a) & (f < bb)
        rows.append(S[m].mean(axis=0) if m.any() else np.full(S.shape[1], np.nan))
    Z = np.log10(np.maximum(np.array(rows), 1e-12))
    Z = np.where(np.isfinite(Z), Z, np.nanmin(Z))
    t0 = float(df.index[0])
    return {"t": [round(float(v) + t0, 2) for v in t], "f": [round(float(v), 2) for v in np.sqrt(edges[:-1] * edges[1:])],
            "log10_psd": np.round(Z, 3).tolist(), "column": col,
            "method": "scipy.signal.spectrogram on the resultant, log-binned for display"}


def _log_decimate(psd: pd.DataFrame, n: int) -> dict:
    f = psd.index.to_numpy()
    if len(f) > n:
        idx = np.unique(np.round(np.logspace(0, np.log10(len(f) - 1), n)).astype(int))
    else:
        idx = np.arange(len(f))
    return {"f": [round(float(v), 3) for v in f[idx]],
            **{c: [float(v) for v in psd[c].to_numpy()[idx]] for c in psd.columns}}
