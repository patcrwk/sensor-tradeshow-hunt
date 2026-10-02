"""Process a participant run: rests -> check-ins -> sequence -> route -> metrics."""
from __future__ import annotations

import numpy as np

from ..config import get_config
from ..detect.identity import BOOTH, identify_rest
from ..detect.qr import match_scans
from ..detect.stillness import Rest, detect_rests
from ..detect.taps import detect_taps, group_taps
from ..io.bundle import Bundle
from ..position.dead_reckoning import detect_steps
from ..position.projection import LocalFrame
from ..position.route import build_route
from .metrics import run_metrics, sensor_view
from .route_compare import compare_legs


def process_run(b: Bundle, course: dict | None, cfg=None, overrides: dict | None = None,
                scans: list[dict] | None = None) -> dict:
    """course: runtime course (see course.survey.runtime_course) or None (Phase 1 mode).

    overrides: {"checkins": [...]} manual check-in list from the review screen;
    when present it replaces automatic identification for sequence and scoring.
    """
    cfg = cfg or get_config()
    st = detect_rests(b, cfg)
    rests = st.rests
    groups = group_taps(detect_taps(b, cfg), cfg)
    qr = None
    if course and "qr" in (course.get("identity_methods") or []):
        qr = match_scans(scans or [], rests, b.meta.get("start_epoch"), cfg)
    idents = [identify_rest(b, r, course, groups, cfg, extra={"qr": qr["per_rest"][i]} if qr else None)
              if course else None for i, r in enumerate(rests)]

    notes: list[str] = []
    start_i, finish_i = _find_start_finish(rests, idents, notes)
    start = rests[start_i] if start_i is not None else None
    finish = rests[finish_i] if finish_i is not None else None

    stations_by_id = {s["id"]: s for s in (course or {}).get("stations", [])}
    checkins, strays = [], []
    for i, (r, idn) in enumerate(zip(rests, idents)):
        if i in (start_i, finish_i):
            continue
        if start is not None and r.end <= start.start or finish is not None and r.start >= finish.end:
            continue  # handling before START / after FINISH
        entry = _entry(r, idn)
        if idn and idn["status"] in ("matched", "review") and idn["station"] not in (None, BOOTH):
            s = stations_by_id.get(idn["station"], {})
            entry.update(station=idn["station"], station_name=s.get("name"), number=s.get("number"))
            checkins.append(entry)
        elif course is None:
            entry.update(station=None, status="unidentified")
            checkins.append(entry)
        else:
            entry["status"] = idn["status"] if idn else "stray"
            strays.append(entry)

    if overrides and overrides.get("checkins") is not None:
        checkins = _apply_overrides(overrides["checkins"], stations_by_id)
        notes.append("check-ins edited by staff")

    seq = sequence_check(checkins, course)
    t0 = start.end if start else (rests[0].end if rests else 0.0)
    t1 = finish.start if finish else (rests[-1].start if len(rests) > 1 else b.duration_s)
    elapsed = t1 - t0 if start and finish else None

    steps = detect_steps(b, cfg, exclude=[(r.start, r.end) for r in rests])
    frame = LocalFrame.from_dict((course or {}).get("frame"))
    mode = (course or {}).get("positioning_mode") or ("gps" if b.has_gps else "dead_reckoning")
    if course is None and b.has_gps and frame is None:
        g = b.gps()
        frame = LocalFrame(float(g["lat"].iloc[0]), float(g["lon"].iloc[0]))
    anchors = _anchors(start, finish, checkins, course)
    route, route_notes = build_route(b, mode, frame, steps, anchors, t0, t1, cfg)
    # Stops without a GPS position take theirs from the route
    if len(route):
        for e in strays + checkins:
            if e.get("x") is None:
                e["x"] = round(float(np.interp(e["rest_mid"], route["t"], route["x"])), 2)
                e["y"] = round(float(np.interp(e["rest_mid"], route["t"], route["y"])), 2)
    legs = compare_legs(route, start, finish, checkins, course)
    metrics = run_metrics(b, route, steps, t0, t1, cfg)
    complete = bool(start and finish and not seq["missing_required"])
    if course is None:
        complete = bool(start and finish)

    needs_review = bool(notes) and not (overrides and overrides.get("checkins") is not None)
    needs_review |= any(c.get("status") == "review" for c in checkins)
    needs_review |= start is None or finish is None
    return {
        "start": start.to_dict() if start else None,
        "finish": finish.to_dict() if finish else None,
        "elapsed_s": round(elapsed, 2) if elapsed is not None else None,
        "elapsed_source": {"method": "end of START rest to start of FINISH rest",
                           "window": [round(t0, 2), round(t1, 2)]},
        "complete": complete,
        "checkins": checkins,
        "strays": strays,
        "rejected_rests": [r.to_dict() for r in st.rejected],
        "sequence": seq,
        "route": {"t": route["t"].round(2).tolist(), "x": route["x"].round(2).tolist(),
                  "y": route["y"].round(2).tolist(), "source": route["source"].tolist()},
        "route_notes": route_notes,
        "positioning_mode": route_notes.get("mode", mode),
        "legs": legs,
        "metrics": metrics,
        "steps": steps.to_dict(),
        "sensor_view": sensor_view(b, st, cfg),
        "notes": notes,
        "qr": {k: v for k, v in qr.items() if k != "per_rest"} if qr else None,
        "needs_review": needs_review,
        "has_gps": b.has_gps,
    }


def _entry(r: Rest, idn: dict | None) -> dict:
    return {
        "rest_start": round(r.start, 2), "rest_end": round(r.end, 2), "rest_mid": round(r.mid, 2),
        "duration": round(r.duration, 1), "gravity": r.gravity_unit,
        "tremor_rms_g": round(r.tremor_rms_g, 5),
        "status": idn["status"] if idn else "unidentified",
        "confidence": idn["confidence"] if idn else None,
        "match_distance_m": idn.get("match_distance_m") if idn else None,
        "reason": idn.get("reason") if idn else None,
        "methods": idn["methods"] if idn else [],
        "source": "auto",
        "x": next((m.get("x") for m in (idn or {}).get("methods", []) if m.get("x") is not None), None),
        "y": next((m.get("y") for m in (idn or {}).get("methods", []) if m.get("y") is not None), None),
    }


def _find_start_finish(rests, idents, notes):
    if not rests:
        notes.append("no rests detected")
        return None, None
    if len(rests) == 1:
        notes.append("only one rest detected; FINISH missing")
        return 0, None

    n = len(rests)
    if idents[0] is None:          # no course: first and last rests
        return 0, n - 1

    def station(i):
        return idents[i].get("station")

    booth = [i for i in range(n) if station(i) == BOOTH]
    stations = [i for i in range(n) if station(i) not in (None, BOOTH)]
    if not stations:
        s = booth[0] if booth else 0
        f = booth[-1] if len(booth) > 1 else n - 1
    else:
        # START = last booth rest before the first station; FINISH = first booth rest after the last
        before = [i for i in booth if i < stations[0]]
        after = [i for i in booth if i > stations[-1]]
        s = before[-1] if before else 0
        f = after[0] if after else n - 1
    # Only flag when the assumed rest was identified as something else (a station)
    if station(s) not in (BOOTH, None):
        notes.append("START rest matched a station, not the booth; assumed the first rest")
    if station(f) not in (BOOTH, None):
        notes.append("FINISH rest matched a station, not the booth; assumed the last rest")
    if f == s:
        return s, None
    return s, f


def _anchors(start, finish, checkins, course):
    if not course:
        return []
    booth = course["booth"]
    st = {s["id"]: s for s in course["stations"]}
    out = []
    if start:
        out.append({"t_start": start.start, "t_end": start.end, "x": booth["x"], "y": booth["y"]})
    for c in checkins:
        s = st.get(c.get("station"))
        if s:
            out.append({"t_start": c["rest_start"], "t_end": c["rest_end"], "x": s["x"], "y": s["y"]})
    if finish:
        out.append({"t_start": finish.start, "t_end": finish.end, "x": booth["x"], "y": booth["y"]})
    return out


def sequence_check(checkins: list[dict], course: dict | None) -> dict:
    if not course:
        return {"order": [], "missing_required": [], "duplicates": [], "out_of_order": [], "bonus": []}
    stations = course["stations"]
    order, seen, dups = [], set(), []
    for c in checkins:
        sid = c.get("station")
        if sid is None:
            continue
        if sid in seen:
            dups.append(sid)
            c["duplicate"] = True
            continue
        seen.add(sid)
        order.append(sid)
    required = [s["id"] for s in stations if s.get("required", True)]
    missing = [s for s in required if s not in seen]
    bonus = [s["id"] for s in stations if not s.get("required", True) and s["id"] in seen]
    ooo = []
    if course.get("order_rule") == "fixed":
        num = {s["id"]: s["number"] for s in stations}
        last = 0
        for sid in order:
            if num[sid] < last:
                ooo.append(sid)
            last = max(last, num[sid])
    return {"order": order, "missing_required": missing, "duplicates": dups,
            "out_of_order": ooo, "bonus": bonus, "required": required}


def _apply_overrides(items: list[dict], stations_by_id: dict) -> list[dict]:
    out = []
    for it in sorted(items, key=lambda c: c["rest_start"]):
        s = stations_by_id.get(it.get("station"), {})
        out.append({**it, "station_name": s.get("name"), "number": s.get("number"),
                    "status": it.get("status") or "matched", "source": it.get("source", "manual")})
    return out
