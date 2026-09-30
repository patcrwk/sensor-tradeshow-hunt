"""Per-leg comparison of a participant route with the course reference."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..course.leg_matrix import leg_lookup
from ..detect.identity import BOOTH
from ..position.projection import path_length


def _dist(route: pd.DataFrame, ta: float, tb: float) -> float:
    if not len(route):
        return 0.0
    seg = route[(route["t"] > ta) & (route["t"] < tb)]
    xa, ya = np.interp(ta, route["t"], route["x"]), np.interp(ta, route["t"], route["y"])
    xb, yb = np.interp(tb, route["t"], route["x"]), np.interp(tb, route["t"], route["y"])
    xs = np.concatenate([[xa], seg["x"], [xb]])
    ys = np.concatenate([[ya], seg["y"], [yb]])
    return path_length(xs, ys)


def compare_legs(route: pd.DataFrame, start, finish, checkins: list[dict], course: dict | None) -> list[dict]:
    """Legs START -> check-in -> ... -> FINISH with split times and extra distance."""
    stops = []
    if start:
        stops.append((BOOTH, start.start, start.end, "START"))
    for c in checkins:
        if c.get("duplicate"):
            continue
        stops.append((c.get("station"), c["rest_start"], c["rest_end"], c.get("station_name") or "Stop"))
    if finish:
        stops.append((BOOTH, finish.start, finish.end, "FINISH"))
    lk = leg_lookup(course.get("legs", [])) if course else {}
    t_origin = start.end if start else (stops[0][2] if stops else 0.0)
    legs = []
    for i in range(len(stops) - 1):
        a, b = stops[i], stops[i + 1]
        dist = _dist(route, a[2], b[1])
        ref = lk.get((a[0], b[0])) if a[0] and b[0] else None
        legs.append({
            "from": a[0], "to": b[0], "from_name": a[3], "to_name": b[3],
            "depart": round(a[2], 2), "arrive": round(b[1], 2),
            "leg_time_s": round(b[1] - a[2], 1),
            "split_s": round(b[1] - t_origin, 1),
            "distance_m": round(dist, 1),
            "reference_m": ref["meters"] if ref else None,
            "reference_kind": ref["kind"] if ref else None,
            "extra_m": round(dist - ref["meters"], 1) if ref else None,
        })
    return legs
