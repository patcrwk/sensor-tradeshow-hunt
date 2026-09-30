"""Optional vibration beacons: a station-specific tone picked up during a rest."""
from __future__ import annotations

import numpy as np
from scipy.signal import welch

from ..config import get_config
from ..io.bundle import Bundle


def detect_beacon(b: Bundle, start: float, end: float, cfg=None) -> dict:
    cfg = cfg or get_config()
    c = cfg.beacons
    role = None
    for r in ("hf_accel", "accel"):
        rate = b.role_rate(r)
        if rate and rate >= c.min_sample_rate_hz:
            role = r
            break
    if role is None:
        return {"method": "beacon", "freq_hz": None,
                "detail": f"needs accel sampled at {c.min_sample_rate_hz} Hz or higher"}
    df = b.role(role)
    seg = df[(df["t"] >= start) & (df["t"] <= end)]
    if len(seg) < 256:
        return {"method": "beacon", "freq_hz": None, "detail": "rest too short for FFT"}
    fs = b.role_rate(role)
    X = seg[["x", "y", "z"]].to_numpy(dtype=np.float64)
    X = X - X.mean(axis=0)
    f, P = welch(X, fs=fs, nperseg=min(len(seg), int(fs * 2)), axis=0)
    p = P.sum(axis=1)
    med = float(np.median(p[(f > 20) & (f < 400)])) or 1e-20
    best, best_snr = None, 0.0
    for fc in c.frequencies_hz:
        band = (f >= fc - c.tolerance_hz) & (f <= fc + c.tolerance_hz)
        if not band.any():
            continue
        snr = float(p[band].max() / med)
        if snr > best_snr:
            best, best_snr = fc, snr
    if best is None or best_snr < c.snr_min:
        return {"method": "beacon", "freq_hz": None, "snr": round(best_snr, 1), "detail": "no tone found"}
    return {"method": "beacon", "freq_hz": best, "snr": round(best_snr, 1),
            "detail": f"{best} Hz tone, SNR {best_snr:.0f}"}
