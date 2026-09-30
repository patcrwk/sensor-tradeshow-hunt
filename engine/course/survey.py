"""Turn one or more survey walks into a course: stations, route, legs, par, quality."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from ..config import get_config
from ..detect.beacons import detect_beacon
from ..detect.identity import BOOTH
from ..detect.orientation import angle_deg, is_reserved
from ..detect.stillness import detect_rests
from ..detect.taps import detect_taps, group_taps, label_rest
from ..io.bundle import Bundle
from ..position.dead_reckoning import detect_steps, dr_path, position_at
from ..position.gps_filter import average_fix
from ..position.loop_closure import close_loop
from ..position.projection import LocalFrame, path_length
from ..position.route import build_route
from .leg_matrix import build_matrix
from .quality_report import quality_report


class SurveyError(Exception):
    pass


def analyze_survey(b: Bundle, cfg=None, mode: str | None = None) -> dict:
    """Derive stations and route from one survey walk."""
    cfg = cfg or get_config()
    st = detect_rests(b, cfg, min_rest_s=cfg.course.survey_min_rest_s)
    rests = st.rests
    if len(rests) < 3:
        raise SurveyError(f"found {len(rests)} rests; a survey needs START, at least one station and FINISH "
                          f"(rests of {cfg.course.survey_min_rest_s:.0f} s or longer)")
    start, finish, mids = rests[0], rests[-1], rests[1:-1]
    groups = group_taps(detect_taps(b, cfg), cfg)
    taps = [label_rest(r.start, groups, cfg) for r in mids]
    fixes = [average_fix(b.gps(), r.start, r.end, cfg) if b.has_gps else None for r in mids]
    booth_fixes = [average_fix(b.gps(), r.start, r.end, cfg) if b.has_gps else None for r in (start, finish)]

    q = quality_report(b, start.end, finish.start, fixes, cfg)
    mode = mode or q["recommended_mode"]

    # Local frame origin = booth
    frame = None
    bf = [f for f in booth_fixes if f]
    anyfix = [f for f in fixes if f]
    if bf:
        frame = LocalFrame(np.mean([f["lat"] for f in bf]), np.mean([f["lon"] for f in bf]))
    elif anyfix:
        frame = LocalFrame(anyfix[0]["lat"], anyfix[0]["lon"])

    steps = detect_steps(b, cfg, exclude=[(r.start, r.end) for r in rests])
    L = cfg.steps.step_length_m

    # Station positions
    positions: list[tuple[float, float] | None] = []
    booth_xy = (0.0, 0.0)
    dr_info = None
    if mode == "dead_reckoning":
        raw = dr_path(steps, L, t0=0.0, t_end=b.duration_s)
        closed, dr_info = close_loop(raw, start.mid, finish.mid)
        ox, oy = position_at(closed, start.mid)
        closed["x"] -= ox
        closed["y"] -= oy
        positions = [position_at(closed, r.mid) for r in mids]
        # If some stations have GPS, rotate the dead-reckoning frame to match north
        if frame is not None:
            closed, positions, dr_info["aligned_to_gps"] = _align_to_gps(closed, positions, fixes, frame)
        route = closed[(closed["t"] >= start.mid) & (closed["t"] <= finish.mid)].copy()
        route["source"] = "reconstructed"
    else:
        if frame is not None and bf:
            bx, by = frame.to_xy(bf[0]["lat"], bf[0]["lon"])
            booth_xy = (float(bx), float(by)) if len(bf) == 1 else (0.0, 0.0)
        for f in fixes:
            positions.append(tuple(float(v) for v in frame.to_xy(f["lat"], f["lon"])) if f else None)
        anchors = [{"t_start": start.start, "t_end": start.end, "x": booth_xy[0], "y": booth_xy[1]}]
        route, _ = build_route(b, mode, frame, steps, anchors, start.mid, finish.mid, cfg)
        # Stations without a fix take their position from the route
        for i, r in enumerate(mids):
            if positions[i] is None and len(route):
                positions[i] = (float(np.interp(r.mid, route["t"], route["x"])),
                                float(np.interp(r.mid, route["t"], route["y"])))

    # Station numbering: tap labels when every station has a unique one
    tap_counts = [t.get("count") for t in taps]
    by_tap = all(tap_counts) and len(set(tap_counts)) == len(tap_counts)
    stations = []
    for i, r in enumerate(mids):
        number = tap_counts[i] if by_tap else i + 1
        f = fixes[i]
        x, y = positions[i]
        acc = f["accuracy_m"] if f and mode != "dead_reckoning" else None
        beacon = detect_beacon(b, r.start, r.end, cfg)
        stations.append({
            "id": f"S{number}", "number": number, "name": f"Station {number}",
            "x": round(x, 2), "y": round(y, 2),
            "lat": f["lat"] if f else None, "lon": f["lon"] if f else None,
            "accuracy_m": round(acc, 1) if acc else None,
            "gps_fixes": f["n"] if f else 0,
            "orientation": r.gravity_unit,
            "reserved_pose": is_reserved(r.gravity_unit, cfg),
            "tap_count": tap_counts[i],
            "beacon_hz": beacon.get("freq_hz"),
            "required": True,
            "rest": {"start": round(r.start, 2), "end": round(r.end, 2), "duration": round(r.duration, 1)},
            "source": {"channels": ["gps"] if acc else ["accel", "gyro"],
                       "window": [round(r.start, 1), round(r.end, 1)],
                       "method": "quality-weighted mean of GPS fixes during the rest" if acc
                       else "dead-reckoning position at rest midpoint (loop closed)"},
        })
    stations.sort(key=lambda s: s["number"])

    # Booth
    booth = {"x": booth_xy[0], "y": booth_xy[1], "orientation": start.gravity_unit,
             "lat": frame.lat0 if frame else None, "lon": frame.lon0 if frame else None,
             "accuracy_m": round(float(np.mean([f["accuracy_m"] for f in bf])), 1) if bf else None}

    # Walked legs along the reference route, in walk order
    order = [BOOTH] + [f"S{tap_counts[i] if by_tap else i + 1}" for i in range(len(mids))] + [BOOTH]
    windows = [start] + mids + [finish]
    walked = []
    for i in range(len(windows) - 1):
        a, bb = windows[i], windows[i + 1]
        seg = route[(route["t"] >= a.end) & (route["t"] <= bb.start)]
        pa = _pos_at(route, a.end)
        pb = _pos_at(route, bb.start)
        xs = np.concatenate([[pa[0]], seg["x"], [pb[0]]])
        ys = np.concatenate([[pa[1]], seg["y"], [pb[1]]])
        walked.append({"from": order[i], "to": order[i + 1], "meters": round(path_length(xs, ys), 1),
                       "seconds": round(bb.start - a.end, 1)})

    walk_s = finish.start - start.end
    extra_rest = sum(max(0.0, r.duration - cfg.course.participant_rest_s) for r in mids)
    par = walk_s - extra_rest

    return {
        "frame": frame.to_dict() if frame else None,
        "mode": mode,
        "quality": q,
        "stations": stations,
        "booth": booth,
        "route": {"t": route["t"].round(2).tolist(), "x": route["x"].round(2).tolist(),
                  "y": route["y"].round(2).tolist(), "source": mode if mode != "dead_reckoning" else "reconstructed"},
        "walked": walked,
        "walk_order": order,
        "par": {"survey_walk_s": round(walk_s, 1), "extra_rest_trimmed_s": round(extra_rest, 1),
                "par_time_s": round(par, 1),
                "source": {"method": "survey time from end of START rest to start of FINISH rest, "
                                     "station rests trimmed to participant rest length"}},
        "rests": [r.to_dict() for r in rests],
        "rejected_rests": [r.to_dict() for r in st.rejected],
        "steps": steps.to_dict(),
        "dead_reckoning": dr_info,
        "taps_used_for_numbering": bool(by_tap),
    }


def _pos_at(route: pd.DataFrame, t: float):
    if not len(route):
        return (0.0, 0.0)
    return float(np.interp(t, route["t"], route["x"])), float(np.interp(t, route["t"], route["y"]))


def _align_to_gps(path, positions, fixes, frame):
    pairs = [(positions[i], frame.to_xy(f["lat"], f["lon"])) for i, f in enumerate(fixes) if f]
    if len(pairs) < 2:
        return path, positions, False
    P = np.array([p for p, _ in pairs])
    Q = np.array([[float(q[0]), float(q[1])] for _, q in pairs])
    # rotation + translation (no scale), Kabsch in 2D
    pc, qc = P.mean(0), Q.mean(0)
    H = (P - pc).T @ (Q - qc)
    ang = np.arctan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1])
    c, s = np.cos(ang), np.sin(ang)

    def tf(x, y):
        x0, y0 = np.asarray(x) - pc[0], np.asarray(y) - pc[1]
        return c * x0 - s * y0 + qc[0], s * x0 + c * y0 + qc[1]

    path = path.copy()
    path["x"], path["y"] = tf(path["x"].to_numpy(), path["y"].to_numpy())
    # keep booth at the origin of the local frame by re-centering on the path start
    positions = [tuple(float(v) for v in tf(p[0], p[1])) for p in positions]
    return path, positions, True


def merge_surveys(results: list[dict], cfg=None) -> dict:
    """Average station coordinates across several surveys of the same course."""
    cfg = cfg or get_config()
    base = results[0]
    if len(results) == 1:
        return base
    frame = LocalFrame.from_dict(base["frame"])
    extra_walked = []
    for other in results[1:]:
        if frame is None or other["mode"] == "dead_reckoning" or base["mode"] == "dead_reckoning":
            base.setdefault("notes", []).append("extra survey not averaged: dead-reckoning frames differ")
            continue
        ofr = LocalFrame.from_dict(other["frame"])
        idmap = {}
        for s in other["stations"]:
            if s["lat"] is None:
                continue
            x, y = frame.to_xy(s["lat"], s["lon"])
            if base["taps_used_for_numbering"] and other["taps_used_for_numbering"]:
                tgt = next((b for b in base["stations"] if b["number"] == s["number"]), None)
            else:
                tgt = min(base["stations"], key=lambda b: np.hypot(b["x"] - x, b["y"] - y))
            if tgt is None:
                continue
            idmap[s["id"]] = tgt["id"]
            tgt.setdefault("_obs", [(tgt["lat"], tgt["lon"], tgt["accuracy_m"] or 10)])
            tgt["_obs"].append((s["lat"], s["lon"], s["accuracy_m"] or 10))
        for w in other["walked"]:
            a = BOOTH if w["from"] == BOOTH else idmap.get(w["from"])
            b2 = BOOTH if w["to"] == BOOTH else idmap.get(w["to"])
            if a and b2:
                extra_walked.append({**w, "from": a, "to": b2})
        _ = ofr
    for s in base["stations"]:
        obs = s.pop("_obs", None)
        if not obs:
            continue
        w = np.array([1 / o[2] ** 2 for o in obs])
        lat = float(np.sum([o[0] for o in obs] * w) / w.sum())
        lon = float(np.sum([o[1] for o in obs] * w) / w.sum())
        x, y = frame.to_xy(lat, lon)
        s.update(lat=lat, lon=lon, x=round(float(x), 2), y=round(float(y), 2),
                 accuracy_m=round(float(np.min([o[2] for o in obs])), 1), surveys=len(obs))
    base["walked"] = base["walked"] + extra_walked
    base["survey_count"] = len(results)
    return base


def finalize(course: dict, cfg=None) -> dict:
    """Add leg matrix, identity-method defaults, spacing warnings."""
    cfg = cfg or get_config()
    legs, detour = build_matrix(course, course["walked"], cfg)
    course["legs"] = legs
    course["detour_factor"] = detour
    q = course["quality"]
    course.setdefault("match_radius_m", q["recommended_radius_m"])
    course.setdefault("positioning_mode", course["mode"])
    course.setdefault("order_rule", "any")
    if "identity_methods" not in course:
        course["identity_methods"] = default_methods(course, cfg)
    course["warnings"] = spacing_warnings(course, cfg)
    return course


def default_methods(course: dict, cfg=None) -> list[str]:
    cfg = cfg or get_config()
    m = []
    q = course["quality"]
    if course["positioning_mode"] != "dead_reckoning":
        m.append("gps")
    st = course["stations"]
    vecs = [s["orientation"] for s in st] + [course["booth"]["orientation"]]
    distinct = all(angle_deg(a, b) > cfg.orientation.min_holder_separation_deg for a, b in itertools.combinations(vecs, 2))
    if distinct and not any(s["reserved_pose"] for s in st):
        m.append("orientation")
    if course.get("taps_used_for_numbering"):
        m.append("taps")
    if st and all(s.get("beacon_hz") for s in st):
        m.append("beacon")
    if not m and q.get("stations_with_fix"):
        m.append("gps")          # poor GPS is still better than no identity at all
    return m or ["orientation"]


def spacing_warnings(course: dict, cfg=None) -> list[str]:
    cfg = cfg or get_config()
    out = []
    radius = course.get("match_radius_m") or cfg.gps.match_radius_m
    need = max(cfg.course.min_station_separation_m, 2 * radius)
    pts = [(s["name"], s["x"], s["y"]) for s in course["stations"]] + [("the booth", course["booth"]["x"], course["booth"]["y"])]
    for (na, xa, ya), (nb, xb, yb) in itertools.combinations(pts, 2):
        d = float(np.hypot(xa - xb, ya - yb))
        if d < need:
            out.append(f"{na} and {nb} are {d:.0f} m apart; with {radius:.0f} m matching they need {need:.0f} m")
    q = course["quality"]
    if q["level"] == "poor" and "gps" in course.get("identity_methods", []):
        out.append("GPS is poor at this venue but is still an identity method; consider holders or tap codes")
    return out


def derive_course(bundles: list[Bundle], cfg=None, mode: str | None = None) -> dict:
    cfg = cfg or get_config()
    results = [analyze_survey(b, cfg, mode) for b in bundles]
    course = merge_surveys(results, cfg)
    return finalize(course, cfg)


def runtime_course(course: dict) -> dict:
    """The subset of a course the hunt matcher needs."""
    return {
        "stations": course["stations"], "booth": course["booth"], "frame": course.get("frame"),
        "identity_methods": course.get("identity_methods", ["gps"]),
        "match_radius_m": course.get("match_radius_m"),
        "positioning_mode": course.get("positioning_mode", "gps"),
        "order_rule": course.get("order_rule", "any"), "legs": course.get("legs", []),
        "par_time_s": course.get("par", {}).get("par_time_s"),
        "route": course.get("route"),
    }
