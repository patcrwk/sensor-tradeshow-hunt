"""Environment tab: pressure to relative altitude, temperature, humidity, light."""
from __future__ import annotations

import numpy as np

from ..io.bundle import Bundle


def pressure_to_altitude(p, p0):
    """International barometric formula, relative to p0 (meters)."""
    p = np.asarray(p, float)
    return 44330.0 * (1.0 - (p / p0) ** (1 / 5.255))


def environment(b: Bundle, max_points: int = 1200) -> dict:
    out: dict = {"available": False}
    env = b.role("env")
    if env is not None and len(env):
        out["available"] = True
        step = max(len(env) // max_points, 1)
        e = env.iloc[::step]
        # Smooth pressure lightly before converting (sensor noise of a few Pa ~ tens of cm)
        p = env["pressure"].rolling(10, center=True, min_periods=1).median() if "pressure" in env else None
        p0 = float(p.iloc[: max(len(p) // 50, 5)].median()) if p is not None else None
        alt = pressure_to_altitude(p.to_numpy(), p0) if p is not None else None
        out["t"] = e["t"].round(2).tolist()
        for c in ("pressure", "temperature", "humidity"):
            if c in e:
                out[c] = e[c].round(3).tolist()
        if alt is not None:
            out["altitude_m"] = np.round(alt[::step], 2).tolist()
            i = int(np.argmax(alt))
            out["altitude"] = {"max_m": round(float(alt.max()), 1), "max_t": round(float(env["t"].iloc[i]), 1),
                               "pressure_drop_pa": round(p0 - float(p.iloc[i]), 1),
                               "min_m": round(float(alt.min()), 1), "p0_pa": round(p0, 1),
                               "source": {"channel": "env.pressure",
                                          "method": "barometric formula relative to the first 2% of the recording"}}
        out["ranges"] = {c: [round(float(env[c].min()), 2), round(float(env[c].max()), 2)]
                         for c in ("pressure", "temperature", "humidity") if c in env}
    env2 = b.role("env2")
    if env2 is not None and len(env2):
        step = max(len(env2) // max_points, 1)
        e2 = env2.iloc[::step]
        out["secondary"] = {"channel": b.roles.get("env2"), "t": e2["t"].round(2).tolist(),
                            **{c: e2[c].round(3).tolist() for c in ("pressure", "temperature", "humidity") if c in e2}}
    light = b.role("light")
    if light is not None and len(light):
        step = max(len(light) // max_points, 1)
        li = light.iloc[::step]
        out["light"] = {"t": li["t"].round(2).tolist(), "lux": li["lux"].round(2).tolist(),
                        "uv": li["uv"].round(3).tolist() if "uv" in li else None,
                        "max_lux": round(float(light["lux"].max()), 2)}
        out["available"] = True
    return out
