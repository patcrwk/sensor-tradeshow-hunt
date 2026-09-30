"""Story tab: an auto-generated highlight timeline.

Rules are small functions registered by name. A profile lists which rules to
run and their parameters; curated annotations from the library can add to or
override what the rules produce.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from ..detect.signal import butter, uniform
from ..io.bundle import Bundle

RULES: dict[str, Callable] = {}


def rule(name):
    def deco(fn):
        RULES[name] = fn
        return fn
    return deco


def fmt_t(t: float) -> str:
    t = max(float(t), 0.0)
    return f"{int(t // 60)}:{int(t % 60):02d}"


def H(t, title, detail, kind, source, value=None):
    return {"t": None if t is None else round(float(t), 2), "time": fmt_t(t) if t is not None else "",
            "title": title, "detail": detail, "kind": kind, "value": value, "source": source}


@rule("duration")
def r_duration(b: Bundle, a: dict, **_):
    d = b.duration_s
    return [H(0, "Recording started", f"{d / 60:.1f} minutes of data across {len(b.meta['channels'])} channels",
              "info", {"method": "recording metadata"})]


@rule("motors")
def r_motors(b: Bundle, a: dict, band=(50.0, 500.0), factor=4.0, **_):
    """Vibration spin-up and spin-down from band-limited RMS."""
    role = "hf_accel" if b.roles.get("hf_accel") else "accel"
    df = b.role(role)
    if df is None:
        return []
    t, A, fs = uniform(df, ["x", "y", "z"])
    hi = min(band[1], fs * 0.45)
    v = np.linalg.norm(butter(A, fs, low=band[0], high=hi), axis=1)
    w = int(fs)
    n = len(v) // w
    if n < 5:
        return []
    rms = np.sqrt((v[: n * w] ** 2).reshape(n, w).mean(axis=1))
    tt = t[: n * w : w] + 0.5
    base = np.percentile(rms, 5)
    on = rms > base * factor
    if not on.any():
        return []
    i0, i1 = int(np.argmax(on)), int(len(on) - 1 - np.argmax(on[::-1]))
    src = {"channel": role, "method": f"1 s RMS of {band[0]:.0f} to {hi:.0f} Hz vibration exceeds {factor:g}x the quietest level"}
    out = [H(tt[i0], "Motors spin up", f"vibration rises to {rms[i0]:.2f} g RMS", "event", src, float(rms[i0]))]
    if i1 < n - 2:
        out.append(H(tt[i1], "Motors stop", "vibration falls back to the quiet level", "event", src))
    return out


@rule("climb")
def r_climb(b: Bundle, a: dict, min_m=2.0, **_):
    alt = a.get("environment", {}).get("altitude")
    env = a.get("environment", {})
    if not alt or alt["max_m"] < min_m:
        return []
    t = np.array(env["t"])
    h = np.array(env["altitude_m"])
    src = alt["source"]
    out = []
    up = np.where(h > 1.0)[0]
    if len(up):
        out.append(H(t[up[0]], "Takeoff", "pressure starts dropping as the sensor climbs", "event", src))
    out.append(H(alt["max_t"], f"Climbed about {alt['max_m']:.0f} m",
                 f"highest point, from a pressure drop of about {alt.get('pressure_drop_pa', alt['max_m'] * 12):.0f} Pa", "peak", src, alt["max_m"]))
    after = np.where((t > alt["max_t"]) & (h < 1.0))[0]
    if len(after):
        out.append(H(t[after[0]], "Landing", "back within 1 m of the starting height", "event", src))
    return out


@rule("dominant_frequency")
def r_freq(b: Bundle, a: dict, band=(20.0, 1000.0), label="Dominant vibration", axis="resultant", **_):
    fr = a.get("frequency", {})
    peaks = [p for p in fr.get("peaks", []) if p["axis"] == axis and band[0] <= p["f_hz"] <= band[1]]
    if not peaks:
        return []
    p = min(peaks, key=lambda p: p["rank"])
    others = sorted({q["f_hz"] for q in fr.get("peaks", []) if q["rank"] == 1 and q["axis"] in ("x", "y", "z")})
    detail = f"strongest {axis} peak in the {band[0]:.0f} to {band[1]:.0f} Hz band"
    if others:
        detail += "; per-axis peaks at " + ", ".join(f"{f:.0f}" for f in others) + " Hz"
    return [H(None, f"{label} near {p['f_hz']:.0f} Hz", detail, "frequency", fr.get("source"), p["f_hz"])]


@rule("peak_event")
def r_peak(b: Bundle, a: dict, **_):
    s = a.get("shock", {})
    if not s.get("events"):
        return []
    e = s["events"][0]
    return [H(e["t"], f"Peak event {e['resultant_g']:.1f} g", f"largest acceleration on {s['channel_name']}",
              "peak", s.get("source"), e["resultant_g"])]


@rule("rotation")
def r_rot(b: Bundle, a: dict, **_):
    m = a.get("motion", {})
    pk = m.get("peaks_dps")
    if not pk:
        return []
    return [H(None, f"Rotation peaks {pk['x']:.0f}, {pk['y']:.0f}, {pk['z']:.0f} deg/s",
              "maximum rotation rate on X, Y and Z", "info", m.get("source"))]


@rule("temperature")
def r_temp(b: Bundle, a: dict, min_change=1.0, **_):
    r = a.get("environment", {}).get("ranges", {}).get("temperature")
    if not r or r[1] - r[0] < min_change:
        return []
    return [H(None, f"Temperature {r[0]:.1f} to {r[1]:.1f} °C", "internal sensor temperature range", "info",
              {"channel": "env.temperature", "method": "min and max"})]


@rule("light")
def r_light(b: Bundle, a: dict, **_):
    li = a.get("environment", {}).get("light")
    if not li:
        return []
    if li["max_lux"] <= 0.5:
        return [H(None, "Dark the whole time", "light sensor read 0 lux throughout; the sensor was enclosed",
                  "info", {"channel": "light", "method": "max lux"})]
    return [H(None, f"Light up to {li['max_lux']:.0f} lux", "brightest reading", "info",
              {"channel": "light", "method": "max lux"})]


@rule("gps_distance")
def r_gps(b: Bundle, a: dict, **_):
    g = a.get("gps", {})
    if not g.get("available"):
        return []
    return [H(None, f"Travelled {g['distance_m']:.0f} m", f"GPS fix {g['fix_ratio']:.0%} of the time", "info",
              {"channel": "gps", "method": "length of quality-filtered GPS track"})]


def build_story(b: Bundle, analysis: dict, profile: dict, annotations: list[dict] | None = None) -> dict:
    items = []
    for spec in profile.get("story_rules", []):
        name, params = (spec, {}) if isinstance(spec, str) else (spec["rule"], spec.get("params", {}))
        fn = RULES.get(name)
        if not fn:
            continue
        try:
            items.extend(fn(b, analysis, **params))
        except Exception as ex:  # a failing rule must not break the tab
            items.append(H(None, f"({name} unavailable)", str(ex)[:120], "error", {}))
    for ann in annotations or []:
        if ann.get("replaces"):
            items = [i for i in items if not i["title"].startswith(ann["replaces"])]
        items.append(H(ann.get("t"), ann["title"], ann.get("detail", ""), "curated", {"method": "curated annotation"}))
    timed = sorted([i for i in items if i["t"] is not None], key=lambda i: i["t"])
    facts = [i for i in items if i["t"] is None]
    return {"timeline": timed, "facts": facts, "profile": profile["id"]}
