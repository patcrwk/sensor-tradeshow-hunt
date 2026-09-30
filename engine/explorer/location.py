"""Motion and Location tab: rotation rates, integrated attitude, GPS track."""
from __future__ import annotations

import numpy as np

from ..config import get_config
from ..detect.signal import butter, uniform
from ..io.bundle import Bundle
from ..position.gps_filter import filtered_track, valid_mask
from ..position.projection import LocalFrame, path_length


def motion(b: Bundle, max_points: int = 1500) -> dict:
    out: dict = {"available": False}
    gyro = b.role("gyro")
    if gyro is not None and len(gyro) > 10:
        t, G, fs = uniform(gyro, ["x", "y", "z"])
        quiet = np.linalg.norm(G, axis=1) < get_config().stillness.gyro_max_dps
        bias = np.median(G[quiet], axis=0) if quiet.sum() > fs else np.zeros(3)
        ang = np.cumsum((G - bias) / fs, axis=0)
        step = max(len(t) // max_points, 1)
        out.update(available=True, t=np.round(t[::step], 2).tolist(),
                   rate={k: np.round(G[::step, i], 2).tolist() for i, k in enumerate("xyz")},
                   integrated_deg={k: np.round(ang[::step, i], 1).tolist() for i, k in enumerate("xyz")},
                   peaks_dps={k: round(float(gyro[k].abs().max()), 1) for k in "xyz"},
                   gyro_channel=b.roles.get("gyro"),
                   source={"channel": "gyro", "method": "rates integrated after removing bias measured while still; "
                                                       "drifts over time, shown for shape not absolute angle"})
    acc = b.role("accel")
    if acc is not None and len(acc) > 10:
        t, A, fs = uniform(acc, ["x", "y", "z"])
        g = butter(A, fs, high=0.5)
        roll = np.degrees(np.arctan2(g[:, 1], g[:, 2]))
        pitch = np.degrees(np.arctan2(-g[:, 0], np.hypot(g[:, 1], g[:, 2])))
        step = max(len(t) // max_points, 1)
        out["tilt"] = {"t": np.round(t[::step], 2).tolist(), "roll_deg": np.round(roll[::step], 1).tolist(),
                       "pitch_deg": np.round(pitch[::step], 1).tolist(),
                       "source": {"channel": "accel", "method": "gravity direction from 0.5 Hz low-pass"}}
    return out


def gps_track(b: Bundle, color_by: list[str] | None = None) -> dict:
    if not b.has_gps:
        return {"available": False, "reason": "no location channel in this recording"}
    cfg = get_config()
    g = b.gps()
    ok = valid_mask(g, cfg)
    if not ok.any():
        return {"available": False, "reason": "location channel present but no valid fix"}
    first = g[ok].iloc[0]
    frame = LocalFrame(float(first["lat"]), float(first["lon"]))
    tr = filtered_track(g, frame, cfg, smooth=False)
    out = {"available": True, "frame": frame.to_dict(), "t": tr["t"].round(2).tolist(),
           "x": tr["x"].round(2).tolist(), "y": tr["y"].round(2).tolist(),
           "sigma_m": tr["sigma"].round(1).tolist(), "distance_m": round(path_length(tr["x"], tr["y"]), 1),
           "fix_ratio": round(float(ok.mean()), 3), "colors": {}}
    tt = tr["t"].to_numpy()
    if "speed" in g:
        out["colors"]["speed"] = np.round(np.interp(tt, g["t"], g["speed"]), 2).tolist()
    if "alt" in g:
        out["colors"]["gps_altitude"] = np.round(np.interp(tt, g["t"], g["alt"]), 1).tolist()
    env = b.role("env")
    if env is not None and "pressure" in env:
        p = env["pressure"].to_numpy()
        out["colors"]["baro_altitude"] = np.round((p[0] - np.interp(tt, env["t"], p)) / 12.0, 2).tolist()
    acc = b.role("accel")
    if acc is not None and len(acc) > 10:
        t, A, fs = uniform(acc, ["x", "y", "z"])
        v = np.linalg.norm(butter(A, fs, low=5.0), axis=1)
        w = max(int(fs), 1)
        rms = np.sqrt(np.convolve(v ** 2, np.ones(w) / w, mode="same"))
        out["colors"]["vibration_rms_g"] = np.round(np.interp(tt, t, rms), 4).tolist()
    return out
