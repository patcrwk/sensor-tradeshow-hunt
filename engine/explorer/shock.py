"""Shock and Events tab: peak events, SRS, shock/vibe metrics via endaq.calc."""
from __future__ import annotations

import warnings

import numpy as np
import endaq.calc.shock as eshock
import endaq.calc.stats as estats

from ..io.bundle import Bundle
from .frequency import accel_frame


def shock(b: Bundle, role: str = "accel", n_events: int = 8, min_spacing_s: float = 5.0) -> dict:
    got = accel_frame(b, role)
    if got is None:
        return {"available": False}
    df, info = got
    xyz = df[["x", "y", "z"]]
    # Peak events are found on the resultant (endaq.calc.stats.find_peaks returns indices)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        idx = estats.find_peaks(df[["resultant"]], time_distance=min_spacing_s, threshold_multiplier=0.3)
    idx = np.asarray(idx, dtype=int)
    res = df["resultant"].to_numpy()
    t = df.index.to_numpy()
    order = idx[np.argsort(res[idx])[::-1]][:n_events] if len(idx) else np.array([int(np.argmax(res))])
    events = []
    for i in sorted(order.tolist(), key=lambda i: -res[i]):
        events.append({"t": round(float(t[i]), 3), "resultant_g": round(float(res[i]), 3),
                       **{f"{c}_g": round(float(xyz[c].iloc[i]), 3) for c in ("x", "y", "z")}})
    fs = info.get("rate_hz") or 1.0
    srs = []
    for e in events[:3]:
        srs.append(event_srs(xyz, e["t"], fs))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            win = xyz.loc[events[0]["t"] - 1.0: events[0]["t"] + 1.0]
            m = estats.shock_vibe_metrics(win, include_integration=True, include_resultant=True,
                                          init_freq=max(2.0, 4 * fs / len(win)), display_plots=False)
            metrics = _metrics_table(m)
        except Exception as ex:  # metrics are optional
            metrics = {"error": str(ex)}
    rms = float(np.sqrt(np.mean((res - np.median(res)) ** 2)))
    return {
        "available": True, "channel": info["id"], "channel_name": info["name"],
        "events": events, "srs": srs, "metrics": metrics,
        "summary": {"peak_g": events[0]["resultant_g"] if events else None,
                    "peak_t": events[0]["t"] if events else None,
                    "vibration_rms_g": round(rms, 4)},
        "source": {"channel": info["name"],
                   "method": "endaq.calc.stats.find_peaks on the resultant; SRS via endaq.calc.shock.shock_spectrum "
                             "(5% damping) on a 1 s window around each event"},
    }


def event_srs(xyz, t_event: float, fs: float, half: float = 0.5) -> dict:
    win = xyz.loc[t_event - half: t_event + half]
    win = win - win.median()
    fmin = max(2.0, 2.0 / (2 * half))
    freqs = np.logspace(np.log10(fmin), np.log10(min(fs / 4, 2000)), 60)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = eshock.shock_spectrum(win, freqs=freqs, damp=0.05, mode="srs")
    return {"t": t_event, "f": [round(float(f), 2) for f in s.index],
            **{c: [round(float(v), 4) for v in s[c]] for c in s.columns}}


def _metrics_table(m) -> dict:
    try:
        df = m.reset_index()
        return {"columns": [str(c) for c in df.columns],
                "rows": [[_fmt(v) for v in r] for r in df.to_numpy().tolist()]}
    except Exception:
        return {"raw": str(m)[:2000]}


def _fmt(v):
    if isinstance(v, float):
        return round(v, 4) if np.isfinite(v) else None
    return v if isinstance(v, (int, str)) else str(v)
