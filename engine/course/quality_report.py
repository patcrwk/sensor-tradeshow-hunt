"""Venue GPS quality report and positioning mode recommendation."""
from __future__ import annotations

import numpy as np

from ..config import get_config
from ..position.gps_filter import availability, fix_sigma, valid_mask


def quality_report(b, t0: float, t1: float, station_fixes: list[dict | None], cfg=None) -> dict:
    cfg = cfg or get_config()
    g = cfg.gps
    gps = b.gps() if b.has_gps else None
    avail = availability(gps, t0, t1, cfg)
    accs = [f["accuracy_m"] for f in station_fixes if f]
    at_stations = sum(1 for f in station_fixes if f)
    typical = float(np.median(accs)) if accs else None
    reported = None
    sats = hdop = None
    if gps is not None and len(gps):
        seg = gps[(gps["t"] >= t0) & (gps["t"] <= t1)]
        seg = seg[valid_mask(seg, cfg)]
        if len(seg):
            reported = float(np.median(fix_sigma(seg, cfg)))
            sats = float(seg["sats"].median()) if "sats" in seg else None
            hdop = float(seg["hdop"].median()) if "hdop" in seg else None
    station_cov = at_stations / max(len(station_fixes), 1)
    if gps is None:
        mode, why = "dead_reckoning", "this sensor recorded no GPS channel"
    elif typical is None:
        mode, why = "dead_reckoning", "no usable fix at any station"
    elif avail >= g.good_fix_ratio and station_cov >= 0.99 and typical <= g.good_accuracy_m:
        mode, why = "gps", f"fix {avail:.0%} of the walk, stations accurate to about {typical:.0f} m"
    elif avail >= g.usable_fix_ratio and station_cov >= 0.8 and typical <= g.usable_accuracy_m:
        mode, why = "fused", f"fix {avail:.0%} of the walk, stations about {typical:.0f} m; steps will bridge gaps"
    else:
        parts = [f"fix only {avail:.0%} of the walk"]
        if typical:
            parts.append(f"stations about {typical:.0f} m")
        mode, why = "dead_reckoning", ", ".join(parts)
    radius = g.match_radius_m
    if typical:
        radius = float(np.clip(g.radius_sigma_factor * typical, g.min_radius_m, g.max_radius_m))
    level = {"gps": "good", "fused": "fair", "dead_reckoning": "poor"}[mode]
    return {
        "has_gps": gps is not None,
        "fix_availability": round(avail, 3),
        "stations_with_fix": at_stations,
        "stations_total": len(station_fixes),
        "typical_station_accuracy_m": round(typical, 1) if typical else None,
        "median_reported_accuracy_m": round(reported, 1) if reported else None,
        "median_satellites": sats,
        "median_hdop": round(hdop, 2) if hdop else None,
        "recommended_mode": mode,
        "recommended_radius_m": round(radius, 1),
        "level": level,
        "explanation": why,
        "source": {"channel": "gps", "window": [round(t0, 1), round(t1, 1)],
                   "method": "share of 1 s bins with an accepted fix; 95% spread of fixes at each station rest"},
    }
