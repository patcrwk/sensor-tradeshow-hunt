"""Build a route in the local metric frame for any positioning mode."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import get_config
from ..io.bundle import Bundle
from .dead_reckoning import Steps, anchor_legs, dr_path
from .fusion import fuse
from .gps_filter import filtered_track
from .projection import LocalFrame

MODES = ("gps", "fused", "dead_reckoning")


def build_route(b: Bundle, mode: str, frame: LocalFrame | None, steps: Steps, anchors: list[dict],
                t0: float, t1: float, cfg=None, step_length: float | None = None) -> tuple[pd.DataFrame, dict]:
    """anchors: identified rests with course positions [{t_start, t_end, x, y}] in time order.

    Returns (points t, x, y, source) and notes. Falls back to dead reckoning
    when GPS is missing for the requested mode.
    """
    cfg = cfg or get_config()
    L = step_length or cfg.steps.step_length_m
    notes: dict = {"mode_requested": mode}
    gps = b.gps() if b.has_gps else None
    if mode in ("gps", "fused") and (gps is None or frame is None):
        notes["fallback"] = "no GPS in this recording; used dead reckoning"
        mode = "dead_reckoning"
    notes["mode"] = mode

    if mode == "gps":
        tr = filtered_track(gps, frame, cfg)
        tr = tr[(tr["t"] >= t0) & (tr["t"] <= t1)]
        if len(tr) < 5:
            notes["fallback"] = "too few good fixes; used dead reckoning"
            return build_route(b, "dead_reckoning", frame, steps, anchors, t0, t1, cfg, L)[0], notes
        pts = tr[["t", "x", "y"]].copy()
        pts["source"] = "gps"
        return pts.reset_index(drop=True), notes

    if mode == "fused":
        tr = filtered_track(gps, frame, cfg, smooth=False)
        tr = tr[(tr["t"] >= t0 - 5) & (tr["t"] <= t1 + 5)]
        # Identified check-ins are strong position fixes at the station coordinates
        anc = [pd.DataFrame({"t": np.arange(a["t_start"], a["t_end"], 2.0), "x": a["x"], "y": a["y"],
                             "sigma": cfg.fusion.anchor_sigma_m}) for a in anchors]
        if anc:
            tr = pd.concat([tr, *anc], ignore_index=True).sort_values("t").reset_index(drop=True)
            notes["station_anchors"] = len(anchors)
        sel = (steps.t >= t0) & (steps.t <= t1)
        st = Steps(steps.t[sel], steps.heading[sel], int(sel.sum()), steps.cadence_spm, steps.walking_s)
        start = (anchors[0]["x"], anchors[0]["y"]) if anchors else None
        pts = fuse(st, tr, L, cfg, start_xy=start, t0=t0, t_end=t1)
        notes["gps_fixes_used"] = int(len(tr))
        return pts, notes

    # dead reckoning
    raw = dr_path(steps, L, t0=min(t0, steps.t[0] if len(steps.t) else t0), t_end=t1)
    if len(anchors) >= 2:
        pts, leg_notes = anchor_legs(raw, anchors, cfg)
        notes["legs"] = leg_notes
    else:
        pts = raw.copy()
        pts["source"] = "reconstructed"
        notes["unanchored"] = True
    pts = pts[(pts["t"] >= t0 - 1e-6) & (pts["t"] <= t1 + 1e-6)]
    return pts.reset_index(drop=True)[["t", "x", "y", "source"]], notes
