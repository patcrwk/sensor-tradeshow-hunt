"""Loop closure for dead-reckoning surveys: START and FINISH are the same point."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .projection import cumdist


def close_loop(path: pd.DataFrame, t_start: float | None = None, t_end: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Distribute the end-point error back along the path in proportion to distance."""
    p = path.copy()
    if len(p) < 2:
        return p, {"closure_error_m": 0.0}
    t0 = p["t"].iloc[0] if t_start is None else t_start
    t1 = p["t"].iloc[-1] if t_end is None else t_end
    x0, y0 = np.interp(t0, p["t"], p["x"]), np.interp(t0, p["t"], p["y"])
    x1, y1 = np.interp(t1, p["t"], p["x"]), np.interp(t1, p["t"], p["y"])
    ex, ey = x1 - x0, y1 - y0
    cd = cumdist(p["x"], p["y"])
    d0 = np.interp(t0, p["t"], cd)
    d1 = np.interp(t1, p["t"], cd)
    frac = np.clip((cd - d0) / max(d1 - d0, 1e-6), 0, 1)
    p["x"] = p["x"] - ex * frac
    p["y"] = p["y"] - ey * frac
    total = float(d1 - d0)
    err = float(np.hypot(ex, ey))
    return p, {"closure_error_m": round(err, 2), "path_length_m": round(total, 1),
               "closure_error_pct": round(100 * err / total, 1) if total else None}
