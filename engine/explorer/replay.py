"""Reconstructed replay: a compact per-frame track for a 3D animation.

Everything comes from the sensor:
    attitude   gyro integrated as a quaternion, with roll and pitch corrected
               toward gravity from the low-passed DC accelerometer (Mahony
               complementary filter). Yaw is gyro only and drifts slowly.
    altitude   pressure, barometric formula, relative to the start.
    activity   band-limited vibration RMS (motors or propellers), 0 to 1.
    position   GPS track when the recording has one; otherwise the object is
               shown in place, because integrating acceleration twice drifts
               by hundreds of meters within seconds.

The first seconds of gravity define "level": the sensor's mounting in the
object is unknown, so the object is assumed level at the start.
"""
from __future__ import annotations

import numpy as np

from ..config import get_config
from ..detect.signal import butter, uniform
from ..io.bundle import Bundle
from ..position.gps_filter import filtered_track, valid_mask
from ..position.projection import LocalFrame
from .environment import pressure_to_altitude


def _qmul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def _q_from_two(u, v):
    """Quaternion rotating unit vector u onto v."""
    u = u / np.linalg.norm(u)
    v = v / np.linalg.norm(v)
    d = float(np.dot(u, v))
    if d < -0.999999:
        axis = np.cross(u, [1, 0, 0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(u, [0, 1, 0])
        axis /= np.linalg.norm(axis)
        return np.array([0.0, *axis])
    c = np.cross(u, v)
    q = np.array([1 + d, *c])
    return q / np.linalg.norm(q)


def _rotate_inv(q, v):
    """Rotate world vector v into the body frame (q maps body to world)."""
    w, x, y, z = q
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                  [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                  [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
    return R.T @ v


def attitude(b: Bundle, fps: float, cfg, kp: float = 1.0, ki: float = 0.02) -> dict | None:
    gyro = b.role("gyro")
    acc = b.role("accel")
    if gyro is None or acc is None or len(gyro) < 20:
        return None
    tg, G, fsg = uniform(gyro, ["x", "y", "z"])
    ta, A, fsa = uniform(acc, ["x", "y", "z"])
    # Gravity estimate: strong low-pass removes propeller and footstep vibration
    Alp = butter(A, fsa, high=2.0)
    Ag = np.column_stack([np.interp(tg, ta, Alp[:, i]) for i in range(3)])
    quiet = np.linalg.norm(G, axis=1) < cfg.stillness.gyro_max_dps
    bias = np.median(G[quiet], axis=0) if quiet.sum() > fsg else np.zeros(3)
    W = np.radians(G - bias)

    n0 = max(int(2 * fsg), 1)
    g0 = Ag[:n0].mean(axis=0)
    q = _q_from_two(g0, np.array([0.0, 0.0, 1.0]))   # body "up" at start -> world up
    integ = np.zeros(3)
    step = max(int(round(fsg / fps)), 1)
    out_t, out_q, trust = [], [], []
    dt = 1.0 / fsg
    for i in range(len(tg)):
        w = W[i].copy()
        a = Ag[i]
        na = np.linalg.norm(a)
        ok = abs(na - 1.0) < 0.25          # only trust accel when near 1 g
        if ok and na > 0:
            v = _rotate_inv(q, np.array([0.0, 0.0, 1.0]))
            e = np.cross(a / na, v)
            integ += ki * e * dt
            w = w + kp * e + integ
        dq = 0.5 * _qmul(q, np.array([0.0, *w])) * dt
        q = q + dq
        q /= np.linalg.norm(q)
        if i % step == 0:
            out_t.append(tg[i])
            out_q.append(q.copy())
            trust.append(ok)
    Q = np.array(out_q)
    w_, x_, y_, z_ = Q.T
    roll = np.degrees(np.arctan2(2 * (w_ * x_ + y_ * z_), 1 - 2 * (x_ * x_ + y_ * y_)))
    pitch = np.degrees(np.arcsin(np.clip(2 * (w_ * y_ - z_ * x_), -1, 1)))
    yaw = np.degrees(np.unwrap(np.arctan2(2 * (w_ * z_ + x_ * y_), 1 - 2 * (y_ * y_ + z_ * z_))))
    return {"t": np.array(out_t), "q": Q, "roll": roll, "pitch": pitch, "yaw": yaw,
            "accel_trusted": float(np.mean(trust))}


def activity(b: Bundle, t: np.ndarray, band=(50.0, 500.0)) -> np.ndarray | None:
    role = "hf_accel" if b.roles.get("hf_accel") else "accel"
    df = b.role(role)
    if df is None or len(df) < 100:
        return None
    ts, A, fs = uniform(df, ["x", "y", "z"])
    hi = min(band[1], fs * 0.45)
    lo = min(band[0], hi / 4)
    v = np.linalg.norm(butter(A, fs, low=lo, high=hi), axis=1)
    w = max(int(fs / 10), 1)
    n = len(v) // w
    rms = np.sqrt((v[: n * w] ** 2).reshape(n, w).mean(axis=1))
    tr = ts[: n * w: w] + 0.05
    ref = np.percentile(rms, 98) or 1.0
    return np.clip(np.interp(t, tr, rms) / ref, 0, 1.2)


def build_replay(b: Bundle, analysis: dict | None = None, model: str = "sensor", fps: float = 20.0) -> dict:
    cfg = get_config()
    att = attitude(b, fps, cfg)
    dur = b.duration_s
    t = att["t"] if att else np.arange(0, dur, 1 / fps)
    out: dict = {"model": model, "fps": fps, "duration_s": dur, "t": np.round(t, 3).tolist(), "notes": []}
    if att:
        out["q"] = np.round(att["q"], 5).tolist()
        out["roll"] = np.round(att["roll"], 1).tolist()
        out["pitch"] = np.round(att["pitch"], 1).tolist()
        out["yaw"] = np.round(att["yaw"], 1).tolist()
        out["notes"].append("Attitude from the gyro, with roll and pitch pulled toward gravity from the "
                            "accelerometer. Heading uses the gyro alone and drifts slowly.")
    else:
        out["notes"].append("No gyro and accelerometer pair: orientation not shown.")

    env = b.role("env")
    if env is not None and "pressure" in env and len(env) > 10:
        p = env["pressure"].rolling(10, center=True, min_periods=1).median().to_numpy()
        p0 = float(np.median(p[: max(len(p) // 50, 5)]))
        alt = pressure_to_altitude(np.interp(t, env["t"], p), p0)
        out["altitude_m"] = np.round(alt, 2).tolist()
        out["notes"].append("Height from air pressure (barometric formula), relative to the start.")
        if "temperature" in env:
            out["temperature_c"] = np.round(np.interp(t, env["t"], env["temperature"]), 2).tolist()

    act = activity(b, t)
    if act is not None:
        out["activity"] = np.round(act, 3).tolist()

    acc = b.role("accel")
    if acc is not None and len(acc) > 10:
        mag = np.linalg.norm(acc[["x", "y", "z"]].to_numpy(np.float64), axis=1)
        w = max(len(mag) // len(t), 1)
        n = len(mag) // w
        pk = mag[: n * w].reshape(n, w).max(axis=1)
        out["accel_g"] = np.round(np.interp(t, acc["t"].to_numpy()[: n * w: w], pk), 2).tolist()

    if b.has_gps:
        g = b.gps()
        ok = valid_mask(g, cfg)
        if ok.sum() > 5:
            first = g[ok].iloc[0]
            fr = LocalFrame(float(first["lat"]), float(first["lon"]))
            tr = filtered_track(g, fr, cfg)
            if len(tr) > 5:
                out["x"] = np.round(np.interp(t, tr["t"], tr["x"]), 2).tolist()
                out["y"] = np.round(np.interp(t, tr["t"], tr["y"]), 2).tolist()
                out["notes"].append("Horizontal position from GPS.")
    if "x" not in out:
        out["notes"].append("No GPS in this recording, so horizontal movement is not shown: the object "
                            "climbs, tilts and turns in place.")

    events = []
    if analysis and analysis.get("shock", {}).get("events"):
        for e in analysis["shock"]["events"][:8]:
            events.append({"t": e["t"], "label": f"{e['resultant_g']:.1f} g"})
    out["events"] = events
    if analysis and analysis.get("story"):
        out["story"] = [{"t": h["t"], "title": h["title"]} for h in analysis["story"]["timeline"] if h["t"] is not None]
    return out
