"""Time Series tab: min/max downsampled windows sized to the viewport."""
from __future__ import annotations

import numpy as np

from ..config import get_config
from ..detect.signal import minmax_downsample
from ..io.bundle import Bundle


def window(b: Bundle, ch_id, t0: float | None = None, t1: float | None = None, n: int = 1500) -> dict:
    if str(ch_id) == "gps":
        df = b.gps()
        if df is None:
            raise KeyError("no gps")
        cols = [c for c in df.columns if c not in ("t", "gps_time")]
    else:
        env = _envelope_window(b, ch_id, t0, t1, n)
        if env is not None:
            return env
        df = b.channel(ch_id)
        cols = [c for c in df.columns if c != "t"]
    t = df["t"].to_numpy()
    i0 = int(np.searchsorted(t, t0)) if t0 is not None else 0
    i1 = int(np.searchsorted(t, t1, side="right")) if t1 is not None else len(t)
    i0, i1 = max(i0 - 1, 0), min(i1 + 1, len(t))
    tt = t[i0:i1]
    out = {"channel": ch_id, "n_raw": int(i1 - i0), "series": {}}
    tc = None
    for c in cols:
        y = df[c].to_numpy()[i0:i1].astype(np.float64)
        tc, lo, hi = minmax_downsample(tt, y, n)
        out["series"][c] = {"min": _clean(lo), "max": _clean(hi)}
    out["t"] = _clean(tc) if tc is not None else []
    out["decimated"] = out["n_raw"] > 2 * n
    return out


def _envelope_window(b: Bundle, ch_id, t0, t1, n: int) -> dict | None:
    """Long recordings: a zoomed-out view uses the min/max envelope (built from every
    full-rate sample) so short spikes stay visible; zoomed in, the averaged data is used."""
    env = b.envelope(ch_id)
    if env is None:
        return None
    t = env["t"].to_numpy()
    i0 = int(np.searchsorted(t, t0)) if t0 is not None else 0
    i1 = int(np.searchsorted(t, t1, side="right")) if t1 is not None else len(t)
    if i1 - i0 < n:
        return None
    i0, i1 = max(i0 - 1, 0), min(i1 + 1, len(t))
    tt = t[i0:i1]
    cols = [c[:-5] for c in env.columns if c.endswith("__min")]
    info = b.channel_info(ch_id) or {}
    out = {"channel": ch_id, "n_raw": int((i1 - i0) * (info.get("decimation") or 1) * get_config().large_recordings.envelope_factor), "series": {}}
    tc = tt
    for c in cols:
        tc, lo, _ = minmax_downsample(tt, env[f"{c}__min"].to_numpy()[i0:i1].astype(np.float64), n)
        _, _, hi = minmax_downsample(tt, env[f"{c}__max"].to_numpy()[i0:i1].astype(np.float64), n)
        out["series"][c] = {"min": _clean(lo), "max": _clean(hi)}
    out["t"] = _clean(tc)
    out["decimated"] = True
    return out


def _clean(a) -> list:
    a = np.asarray(a, dtype=np.float64)
    return [None if not np.isfinite(v) else round(float(v), 6) for v in a]
