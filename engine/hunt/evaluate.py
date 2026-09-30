"""Score engine output against synthetic ground truth."""
from __future__ import annotations

import numpy as np

from ..detect.identity import BOOTH


def truth_station_id(label) -> str | None:
    if label in ("START", "FINISH"):
        return BOOTH
    if isinstance(label, int) or (isinstance(label, str) and label.isdigit()):
        return f"S{int(label)}"
    return None


def checkin_accuracy(result: dict, truth: dict) -> dict:
    """Compare detected check-ins with true station rests.

    correct:  a true station rest detected and assigned to the right station
    wrong:    assigned to a different station
    missed:   a true station rest with no check-in
    false:    a check-in where no station rest happened (stray, hand-held)
    """
    true_rests = [r for r in truth["rests"] if r["kind"] == "station"]
    used = set()
    correct = wrong = missed = 0
    for tr in true_rests:
        sid = truth_station_id(tr["label"])
        hit = None
        for i, c in enumerate(result["checkins"]):
            if i in used:
                continue
            if c["rest_start"] < tr["end"] and c["rest_end"] > tr["start"]:
                hit = i
                break
        if hit is None:
            missed += 1
            continue
        used.add(hit)
        if result["checkins"][hit].get("station") == sid:
            correct += 1
        else:
            wrong += 1
    false = len([i for i in range(len(result["checkins"])) if i not in used])
    n = len(true_rests)
    return {"true_station_rests": n, "correct": correct, "wrong": wrong, "missed": missed,
            "false": false, "accuracy": correct / n if n else 1.0}


def truth_transform(course: dict, truth: dict):
    """Rigid transform (rotation + translation) from the derived course frame to the truth frame,
    fitted on station positions. Dead-reckoning courses have an arbitrary rotation."""
    tst = {f"S{s['number']}": (s["x"], s["y"]) for s in truth["course"]["stations"]}
    P, Q = [], []
    for s in course["stations"]:
        if s["id"] in tst:
            P.append((s["x"], s["y"]))
            Q.append(tst[s["id"]])
    P.append((course["booth"]["x"], course["booth"]["y"]))
    Q.append((truth["course"]["booth"]["x"], truth["course"]["booth"]["y"]))
    P, Q = np.array(P, float), np.array(Q, float)
    pc, qc = P.mean(0), Q.mean(0)
    H = (P - pc).T @ (Q - qc)
    ang = np.arctan2(H[0, 1] - H[1, 0], H[0, 0] + H[1, 1])
    c, s = np.cos(ang), np.sin(ang)

    def tf(x, y):
        x0, y0 = np.asarray(x, float) - pc[0], np.asarray(y, float) - pc[1]
        return c * x0 - s * y0 + qc[0], s * x0 + c * y0 + qc[1]
    return tf


def station_errors(course: dict, truth: dict, aligned: bool = False) -> list[dict]:
    tf = truth_transform(course, truth) if aligned else (lambda x, y: (x, y))
    tst = {f"S{s['number']}": s for s in truth["course"]["stations"]}
    out = []
    for s in course["stations"]:
        t = tst.get(s["id"])
        if not t:
            continue
        x, y = tf(s["x"], s["y"])
        out.append({"id": s["id"], "error_m": round(float(np.hypot(x - t["x"], y - t["y"])), 2),
                    "accuracy_m": s.get("accuracy_m")})
    return out


def route_deviation(result: dict, truth: dict, tf=None) -> dict:
    rt = np.array(result["route"]["t"])
    if len(rt) < 2:
        return {"median_m": None, "p90_m": None}
    tt = np.array(truth["path"]["t"])
    tx = np.array(truth["path"]["x"])
    ty = np.array(truth["path"]["y"])
    rx = np.interp(tt, rt, result["route"]["x"])
    ry = np.interp(tt, rt, result["route"]["y"])
    if tf is not None:
        rx, ry = tf(rx, ry)
    sel = (tt >= rt[0]) & (tt <= rt[-1])
    d = np.hypot(rx[sel] - tx[sel], ry[sel] - ty[sel])
    return {"median_m": round(float(np.median(d)), 2), "p90_m": round(float(np.percentile(d, 90)), 2)}


def passes_stations_in_order(result: dict, truth: dict, tol_m: float, course: dict | None = None) -> bool:
    """Route passes within tol of every visited station, in visit order.

    Stations are taken from the course (the frame the route is drawn in) when
    given, else from the truth."""
    rt = np.array(result["route"]["t"])
    rx = np.array(result["route"]["x"])
    ry = np.array(result["route"]["y"])
    stations = {s["number"]: s for s in (course or truth["course"])["stations"]}
    last_i = 0
    for n in truth["visits"]:
        s = stations[n]
        d = np.hypot(rx[last_i:] - s["x"], ry[last_i:] - s["y"])
        near = np.where(d <= tol_m)[0]
        if not len(near):
            return False
        last_i += int(near[0])
    return len(rt) > 0
