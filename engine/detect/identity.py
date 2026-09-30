"""Decide which station a rest belongs to, using the course's identity methods."""
from __future__ import annotations

import numpy as np

from ..config import get_config
from ..io.bundle import Bundle
from ..position.gps_filter import average_fix
from ..position.projection import LocalFrame
from .beacons import detect_beacon
from .orientation import match_orientation
from .stillness import Rest
from .taps import label_rest

BOOTH = "BOOTH"


def identify_rest(b: Bundle, rest: Rest, course: dict, tap_groups: list[dict], cfg=None) -> dict:
    """Return {station, status, methods: [...], confidence, match_distance_m, ...}.

    status: "matched", "review" (methods disagree), "stray" (no station),
            "reserved" (flat face-up pose, ignored).
    course: {"stations": [{id, number, x, y, orientation, tap_count, beacon_hz}],
             "booth": {x, y, orientation?}, "identity_methods": [...], "match_radius_m",
             "frame": {lat0, lon0}}
    The booth is included as a candidate with id BOOTH.
    """
    cfg = cfg or get_config()
    methods = course.get("identity_methods") or ["gps"]
    cands = list(course.get("stations", []))
    booth = course.get("booth")
    if booth:
        cands = cands + [{**booth, "id": BOOTH, "number": 0}]
    results = []
    for m in methods:
        if m == "gps":
            results.append(_gps(b, rest, cands, course, cfg))
        elif m == "orientation":
            results.append(match_orientation(rest.gravity_unit, cands, cfg))
        elif m == "taps":
            r = label_rest(rest.start, tap_groups, cfg)
            r["station"] = next((s["id"] for s in cands if s.get("tap_count") and s["tap_count"] == r["count"]), None)
            results.append(r)
        elif m == "beacon":
            r = detect_beacon(b, rest.start, rest.end, cfg)
            r["station"] = next((s["id"] for s in cands if s.get("beacon_hz") and r.get("freq_hz")
                                 and abs(s["beacon_hz"] - r["freq_hz"]) < 1), None)
            results.append(r)
    return combine(results)


def _gps(b: Bundle, rest: Rest, cands: list[dict], course: dict, cfg) -> dict:
    frame = LocalFrame.from_dict(course.get("frame"))
    fix = average_fix(b.gps(), rest.start, rest.end, cfg) if b.has_gps else None
    if fix is None or frame is None:
        return {"method": "gps", "station": None, "available": False, "detail": "no usable GPS fix during rest"}
    x, y = frame.to_xy(fix["lat"], fix["lon"])
    x, y = float(x), float(y)
    radius = float(course.get("match_radius_m") or cfg.gps.match_radius_m)
    best, bd = None, 1e18
    for s in cands:
        if s.get("x") is None:
            continue
        d = float(np.hypot(s["x"] - x, s["y"] - y))
        if d < bd:
            best, bd = s["id"], d
    ok = best is not None and bd <= radius
    return {"method": "gps", "station": best if ok else None, "available": True, "nearest": best,
            "distance_m": round(bd, 1), "radius_m": radius, "x": x, "y": y,
            "lat": fix["lat"], "lon": fix["lon"], "n_fixes": fix["n"], "spread_m": round(fix["spread_m"], 1),
            "detail": f"{fix['n']} fixes averaged, {bd:.0f} m from {best}"}


def combine(results: list[dict]) -> dict:
    avail = [r for r in results if r.get("available", True) and not (r["method"] == "taps" and r.get("count") is None)
             and not (r["method"] == "beacon" and r.get("freq_hz") is None)]
    # Reserved pose only counts when orientation is the sole available method,
    # or no other method matched a station.
    reserved = any(r.get("reserved") for r in avail)
    stations = [r.get("station") for r in avail]
    matched = [s for s in stations if s is not None]
    out = {"methods": results}
    if not avail:
        out.update(status="stray", station=None, confidence=0.0, reason="no identity method produced a result")
    elif matched and all(s == matched[0] for s in stations) and not reserved:
        out.update(status="matched", station=matched[0], confidence=1.0 if len(matched) > 1 else 0.85)
    elif matched and len(set(matched)) == 1 and (None in stations or reserved):
        # One method matched, another produced nothing: take it, but flag it
        out.update(status="review", station=matched[0], confidence=0.5,
                   reason="methods disagree: " + _summary(avail))
    elif matched:
        out.update(status="review", station=matched[0], confidence=0.3,
                   reason="methods disagree: " + _summary(avail))
    elif reserved:
        out.update(status="reserved", station=None, confidence=0.0, reason="flat, face up (reserved pose)")
    else:
        out.update(status="stray", station=None, confidence=0.0, reason="no station within range")
    g = next((r for r in results if r["method"] == "gps" and r.get("available")), None)
    out["match_distance_m"] = g.get("distance_m") if g and out.get("station") == g.get("station") else None
    return out


def _summary(rs: list[dict]) -> str:
    return "; ".join(f"{r['method']}={r.get('station') or 'none'}" for r in rs)
