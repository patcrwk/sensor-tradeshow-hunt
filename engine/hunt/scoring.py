"""Leaderboard categories and run summaries."""
from __future__ import annotations

from ..course.leg_matrix import optimal_tour

CATEGORIES = {
    "fastest": {"title": "Fastest", "unit": "time", "desc": "START to FINISH with every required station"},
    "efficient": {"title": "Most efficient", "unit": "pct", "desc": "shortest possible route divided by distance walked"},
    "crew": {"title": "Beat the crew", "unit": "delta", "desc": "time against the crew's par"},
    "steady": {"title": "Steadiest hands", "unit": "g", "desc": "lowest vibration while walking"},
    "steps": {"title": "Most steps", "unit": "count", "desc": "steps counted by the accelerometer"},
    "cadence": {"title": "Highest cadence", "unit": "spm", "desc": "steps per minute while walking"},
    "speed": {"title": "Top walking speed", "unit": "mps", "desc": "fastest sustained walking speed"},
}


def summarize(result: dict, course: dict | None) -> dict:
    """Numbers stored on the Run row for fast leaderboards."""
    m = result.get("metrics", {})
    s = {
        "elapsed_s": result.get("elapsed_s"),
        "complete": result.get("complete"),
        "stations": len(result.get("sequence", {}).get("order", [])) if course else len(result.get("checkins", [])),
        "missing": result.get("sequence", {}).get("missing_required", []),
        "strays": len(result.get("strays", [])),
        "distance_m": m.get("distance_m"),
        "steps": m.get("steps"),
        "cadence_spm": m.get("cadence_spm"),
        "top_speed_mps": m.get("top_speed_mps"),
        "vibration_rms_g": m.get("vibration_rms_g"),
        "peak_g": m.get("peak_g"),
        "peak_g_t": m.get("peak_g_t"),
        "positioning_mode": result.get("positioning_mode"),
        "extra_m": round(sum(l["extra_m"] for l in result.get("legs", []) if l.get("extra_m") is not None), 1)
        if any(l.get("extra_m") is not None for l in result.get("legs", [])) else None,
    }
    if course:
        req = [st["id"] for st in course["stations"] if st.get("required", True)]
        opt, tour = optimal_tour(req, course.get("legs", []))
        s["optimal_m"] = round(opt, 1)
        s["optimal_order"] = tour
        if s["complete"] and s["distance_m"]:
            s["efficiency"] = round(min(opt / s["distance_m"], 1.0), 4)
        par = course.get("par_time_s") or (course.get("par") or {}).get("par_time_s")
        if par and s["elapsed_s"] is not None:
            s["par_s"] = par
            s["vs_par_s"] = round(s["elapsed_s"] - par, 1)
    return s


def leaderboard(rows: list[dict], category: str, limit: int = 10) -> list[dict]:
    """rows: [{run_id, name, summary}] of published runs."""
    def key_fastest(r):
        s = r["summary"]
        return (0 if s.get("complete") else 1, -(s.get("stations") or 0),
                s["elapsed_s"] if s.get("elapsed_s") is not None else 1e12)

    if category == "fastest":
        ranked = sorted([r for r in rows if r["summary"].get("elapsed_s") is not None], key=key_fastest)
        val = lambda r: r["summary"]["elapsed_s"]  # noqa: E731
    elif category == "efficient":
        ranked = sorted([r for r in rows if r["summary"].get("efficiency")], key=lambda r: -r["summary"]["efficiency"])
        val = lambda r: r["summary"]["efficiency"]  # noqa: E731
    elif category == "crew":
        ranked = sorted([r for r in rows if r["summary"].get("vs_par_s") is not None and r["summary"].get("complete")],
                        key=lambda r: r["summary"]["vs_par_s"])
        val = lambda r: r["summary"]["vs_par_s"]  # noqa: E731
    elif category == "steady":
        ranked = sorted([r for r in rows if r["summary"].get("vibration_rms_g")], key=lambda r: r["summary"]["vibration_rms_g"])
        val = lambda r: r["summary"]["vibration_rms_g"]  # noqa: E731
    elif category == "steps":
        ranked = sorted([r for r in rows if r["summary"].get("steps")], key=lambda r: -r["summary"]["steps"])
        val = lambda r: r["summary"]["steps"]  # noqa: E731
    elif category == "cadence":
        ranked = sorted([r for r in rows if r["summary"].get("cadence_spm")], key=lambda r: -r["summary"]["cadence_spm"])
        val = lambda r: r["summary"]["cadence_spm"]  # noqa: E731
    elif category == "speed":
        ranked = sorted([r for r in rows if r["summary"].get("top_speed_mps")], key=lambda r: -r["summary"]["top_speed_mps"])
        val = lambda r: r["summary"]["top_speed_mps"]  # noqa: E731
    else:
        raise KeyError(category)
    out = []
    for i, r in enumerate(ranked[:limit]):
        s = r["summary"]
        out.append({"rank": i + 1, "run_id": r["run_id"], "name": r["name"], "value": val(r),
                    "complete": s.get("complete"), "stations": s.get("stations"),
                    "missing": len(s.get("missing") or []), "mode": s.get("positioning_mode")})
    return out
