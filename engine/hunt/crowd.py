"""Crowd dashboards: totals, histogram, heat map, station order, environment map."""
from __future__ import annotations

from collections import Counter

import numpy as np


def crowd_stats(runs: list[dict], course: dict | None, grid_m: float = 5.0) -> dict:
    """runs: [{run_id, name, summary, result}] of published runs (result may be trimmed)."""
    s = [r["summary"] for r in runs]
    times = [x["elapsed_s"] for x in s if x.get("complete") and x.get("elapsed_s")]
    out = {
        "participants": len(runs),
        "finished": len(times),
        "total_steps": int(sum(x.get("steps") or 0 for x in s)),
        "total_distance_m": round(sum(x.get("distance_m") or 0 for x in s), 1),
        "avg_time_s": round(float(np.mean(times)), 1) if times else None,
        "best_time_s": round(float(np.min(times)), 1) if times else None,
        "histogram": _hist(times),
    }
    # Heat map: count route points per grid cell (each run counted once per cell)
    heat: Counter = Counter()
    env_cells: dict = {}
    orders: Counter = Counter()
    for r in runs:
        res = r.get("result") or {}
        rt = res.get("route") or {}
        xs, ys = rt.get("x") or [], rt.get("y") or []
        cells = {(int(np.floor(x / grid_m)), int(np.floor(y / grid_m))) for x, y in zip(xs, ys)}
        heat.update(cells)
        for e in (res.get("metrics") or {}).get("env_samples") or []:
            k = (int(np.floor(e["x"] / (grid_m * 2))), int(np.floor(e["y"] / (grid_m * 2))))
            c = env_cells.setdefault(k, {"n": 0, "temperature": 0.0, "humidity": 0.0, "lux": 0.0, "nl": 0, "nh": 0, "nt": 0})
            c["n"] += 1
            for f, n in (("temperature", "nt"), ("humidity", "nh"), ("lux", "nl")):
                if e.get(f) is not None:
                    c[f] += e[f]
                    c[n] += 1
        seq = (res.get("sequence") or {}).get("order") or []
        if seq:
            orders[" > ".join(seq)] += 1
    out["heat"] = {"cell_m": grid_m, "cells": [{"i": k[0], "j": k[1], "n": v} for k, v in heat.items()]}
    out["environment"] = {"cell_m": grid_m * 2, "cells": [
        {"i": k[0], "j": k[1], "samples": c["n"],
         "temperature": round(c["temperature"] / c["nt"], 2) if c["nt"] else None,
         "humidity": round(c["humidity"] / c["nh"], 1) if c["nh"] else None,
         "lux": round(c["lux"] / c["nl"], 0) if c["nl"] else None}
        for k, c in env_cells.items()]}
    out["station_orders"] = [{"order": k, "count": v} for k, v in orders.most_common(5)]
    opt = next((x.get("optimal_order") for x in s if x.get("optimal_order")), None)
    out["optimal_order"] = " > ".join(o for o in opt if o != "BOOTH") if opt else None
    out["shock_log"] = sorted(
        [{"run_id": r["run_id"], "name": r["name"], "peak_g": r["summary"].get("peak_g")}
         for r in runs if r["summary"].get("peak_g")], key=lambda x: x["run_id"], reverse=True)[:12]
    return out


def _hist(times: list[float], n: int = 10) -> list[dict]:
    if not times:
        return []
    lo, hi = min(times), max(times)
    if hi - lo < 1:
        return [{"from": lo, "to": hi, "count": len(times)}]
    edges = np.linspace(lo, hi, n + 1)
    counts, _ = np.histogram(times, edges)
    return [{"from": round(float(a), 1), "to": round(float(b), 1), "count": int(c)}
            for a, b, c in zip(edges[:-1], edges[1:], counts)]
