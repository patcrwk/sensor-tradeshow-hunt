"""QR check-ins: match phone scans of station codes to the sensor's rests.

The phone says WHICH station (scan of the station's QR code); the sensor
proves the stop happened (a 10 second rest). Scan times come from the server
clock, rest times from the sensor clock, so the two can disagree by minutes
if the sensor clock was not synced. Instead of trusting either clock, the
whole sequence of scans is slid against the whole sequence of rests and the
offset that pairs the most scans with rests wins.
"""
from __future__ import annotations

import numpy as np

from ..config import get_config


def _pairs(scan_t: np.ndarray, rests: list, offset: float, before: float, after: float) -> list[tuple[int, int, float]]:
    """Greedy one-to-one pairing of scans to rests for a given clock offset.

    A scan pairs with a rest if it happened from `before` seconds before the rest
    started to `after` seconds after it ended. Returns (scan_index, rest_index, gap).
    """
    cand = []
    for i, ts in enumerate(scan_t + offset):
        for j, r in enumerate(rests):
            if r.start - before <= ts <= r.end + after:
                gap = 0.0 if r.start <= ts <= r.end else min(abs(ts - r.start), abs(ts - r.end))
                cand.append((gap, i, j))
    cand.sort()
    used_s, used_r, out = set(), set(), []
    for gap, i, j in cand:
        if i in used_s or j in used_r:
            continue
        used_s.add(i)
        used_r.add(j)
        out.append((i, j, gap))
    return out


def match_scans(scans: list[dict], rests: list, sensor_start_epoch: float | None, cfg=None) -> dict:
    """scans: [{station, at (epoch)}]. Returns {per_rest: [method result per rest], offset_s, matched}."""
    cfg = cfg or get_config()
    c = cfg.qr
    n = len(rests)
    empty = [{"method": "qr", "station": None, "available": False, "detail": "no scan near this rest"}] * n
    if not scans or not rests or sensor_start_epoch is None:
        why = "no scans for this run" if not scans else "recording has no start time"
        return {"per_rest": [dict(e, detail=why) for e in empty], "offset_s": None, "matched": 0}
    scans = sorted(scans, key=lambda s: s["at"])
    scan_t = np.array([s["at"] - sensor_start_epoch for s in scans], float)   # in sensor seconds, before skew

    # Coarse-to-fine search over the clock offset
    best = (-1, 1e18, 0.0)          # (pairs, total gap, offset)
    for step, lo, hi in ((5.0, -c.max_clock_skew_s, c.max_clock_skew_s), (0.5, -10.0, 10.0)):
        center = 0.0 if step == 5.0 else best[2]
        for off in np.arange(center + lo, center + hi + step / 2, step):
            p = _pairs(scan_t, rests, off, c.scan_before_rest_s, c.scan_after_rest_s)
            score = (len(p), -sum(g for *_, g in p) - 0.01 * abs(off))
            if (score[0], score[1]) > (best[0], -best[1]):
                best = (len(p), -score[1], float(off))
    offset = best[2]
    pairs = _pairs(scan_t, rests, offset, c.scan_before_rest_s, c.scan_after_rest_s)

    per_rest = [dict(e) for e in empty]
    for i, j, gap in pairs:
        s = scans[i]
        per_rest[j] = {
            "method": "qr", "station": s["station"], "available": True,
            "scan_at": s["at"], "scan_t": round(float(scan_t[i] + offset), 1), "gap_s": round(gap, 1),
            "detail": f"scanned {s['station_name'] if s.get('station_name') else s['station']} "
                      + ("during the rest" if gap == 0 else f"{gap:.0f} s from the rest"),
        }
    return {"per_rest": per_rest, "offset_s": round(offset, 1), "matched": len(pairs),
            "unmatched_scans": [scans[i]["station"] for i in range(len(scans)) if i not in {p[0] for p in pairs}]}
