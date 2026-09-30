"""Identify a holder by the gravity vector measured during a rest."""
from __future__ import annotations

import numpy as np

from ..config import get_config


def angle_deg(a, b) -> float:
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 180.0
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / (na * nb), -1, 1))))


def is_reserved(g_unit, cfg=None) -> bool:
    """True when the sensor lay flat, face up. That pose is never a station."""
    cfg = cfg or get_config()
    return angle_deg(g_unit, cfg.orientation.reserved_face_up) < cfg.orientation.reserved_tolerance_deg


def match_orientation(g_unit, stations: list[dict], cfg=None) -> dict:
    """stations: [{id, orientation: [x,y,z]}]. Returns a method result dict."""
    cfg = cfg or get_config()
    if is_reserved(g_unit, cfg):
        return {"method": "orientation", "station": None, "reserved": True,
                "angle_deg": angle_deg(g_unit, cfg.orientation.reserved_face_up),
                "detail": "flat, face up (reserved pose)"}
    best, best_ang = None, 999.0
    for s in stations:
        v = s.get("orientation")
        if not v:
            continue
        a = angle_deg(g_unit, v)
        if a < best_ang:
            best, best_ang = s["id"], a
    ok = best is not None and best_ang <= cfg.orientation.match_max_deg
    return {"method": "orientation", "station": best if ok else None, "angle_deg": round(best_ang, 1),
            "nearest": best, "reserved": False,
            "detail": f"gravity vector {best_ang:.0f} deg from holder" if best else "no holder vectors"}
