"""Synthetic recordings with ground truth, written straight to the bundle format.

A scenario is a list of actions (rest, walk, hand-held pause, taps). The
generator turns it into DC acceleration, gyro, pressure/temperature/humidity,
light and GPS streams. Every file carries ground_truth.json: the true course,
visit order, rest windows, path, strays, hand-held pauses and step count.

GPS quality profiles:
    outdoor   2 to 5 m error, slowly correlated
    indoor    10 to 30 m error with drift, higher HDOP, fewer satellites
    dropout   decent fixes, but lost for long stretches (about 60% of the time)
    none      no GPS channel at all
"""
from __future__ import annotations

import io
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..io import bundle as B
from ..position.projection import LocalFrame

ORIGIN = (36.13170, -115.15180)   # a parking lot next to a convention center

# Holder poses (gravity direction in sensor axes). Face up [0,0,1] is reserved.
HOLDERS = [
    [1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0], [0, 0, -1],
    [0.7071, 0, 0.7071], [0, 0.7071, 0.7071], [-0.7071, 0, 0.7071],
]
BOOTH_HOLDER = [0, -0.7071, 0.7071]
FACE_UP = [0.0, 0.0, 1.0]
BEACONS = [47, 73, 113, 157, 199, 241, 283, 331]


@dataclass
class SynthCourse:
    stations: list[dict]            # [{number, name, x, y, holder, tap_count, beacon_hz}]
    booth: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "holder": BOOTH_HOLDER})
    origin: tuple = ORIGIN
    # Aisle-like detour waypoints: {(a, b): [(x, y), ...]} for walking between points
    mezzanine: list[int] = field(default_factory=list)   # station numbers up a level

    def point(self, n: int) -> dict:
        return self.booth if n == 0 else self.stations[n - 1]

    def to_dict(self) -> dict:
        return {"stations": self.stations, "booth": self.booth, "origin": list(self.origin),
                "mezzanine": self.mezzanine}


def default_course(n: int = 6, seed: int = 7) -> SynthCourse:
    pts = [(28, 12), (55, 30), (48, 62), (15, 70), (-18, 48), (-25, 15), (70, -5), (5, 95)][:n]
    st = []
    for i, (x, y) in enumerate(pts):
        st.append({"number": i + 1, "name": f"Station {i + 1}", "x": float(x), "y": float(y),
                   "holder": HOLDERS[i % len(HOLDERS)], "tap_count": i + 1,
                   "beacon_hz": BEACONS[i % len(BEACONS)]})
    return SynthCourse(st)


@dataclass
class Opts:
    gps_profile: str = "outdoor"          # outdoor | indoor | dropout | none
    use_holders: bool = False             # rests at stations use the holder pose
    use_taps: bool = False
    use_beacons: bool = False
    accel_hz: float = 200.0
    gyro_hz: float = 100.0
    speed_mps: float = 1.3
    cadence_hz: float = 1.85
    serial: int = 90001
    start_epoch: float = 1790000000.0     # 2026-09-21
    seed: int = 1
    kind: str = "participant"             # participant | survey


class Gen:
    def __init__(self, course: SynthCourse, o: Opts):
        self.c = course
        self.o = o
        self.rng = np.random.default_rng(o.seed)
        self.fs = o.accel_hz
        self.t = 0.0
        self.acc: list[np.ndarray] = []
        self.gyr: list[np.ndarray] = []
        self.pos: list[np.ndarray] = []
        self.alt: list[np.ndarray] = []
        self.ts: list[np.ndarray] = []
        self.x, self.y = course.booth["x"], course.booth["y"]
        self.heading = self.rng.uniform(-np.pi, np.pi)
        self.level = 0.0
        self.u_walk = _unit([0.15, -0.35, 0.92])    # lanyard pose while walking
        self.g_now = np.array(self.u_walk)
        self.truth = {"rests": [], "hand_held": [], "strays": [], "visits": [], "taps": [],
                      "steps": 0, "path": []}

    # -- primitives ---------------------------------------------------------
    def _emit(self, n, acc, gyr, pos, alt):
        t = self.t + np.arange(n) / self.fs
        self.ts.append(t)
        self.acc.append(acc)
        self.gyr.append(gyr)
        self.pos.append(pos)
        self.alt.append(alt)
        self.t += n / self.fs

    def _n(self, secs):
        return max(int(round(secs * self.fs)), 1)

    def transition(self, g_to, secs=1.2):
        n = self._n(secs)
        g0, g1 = np.array(self.g_now), _unit(g_to)
        w = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n)))[:, None]
        g = g0 * (1 - w) + g1 * w
        g /= np.linalg.norm(g, axis=1, keepdims=True)
        acc = g + self.rng.normal(0, 0.06, (n, 3))
        ang = np.degrees(np.arccos(np.clip(np.dot(g0, g1), -1, 1)))
        axis = np.cross(g0, g1)
        axis = axis / (np.linalg.norm(axis) or 1)
        rate = ang / secs * np.sin(np.linspace(0, np.pi, n)) * (np.pi / 2)
        gyr = axis[None, :] * rate[:, None] + self.rng.normal(0, 2.0, (n, 3))
        self._emit(n, acc, gyr, np.tile([self.x, self.y], (n, 1)), np.full(n, self.level))
        self.g_now = g1

    def rest(self, g, secs, label=None, beacon_hz=None, kind="station"):
        n = self._n(secs)
        gu = _unit(g)
        acc = gu + self.rng.normal(0, 0.0025, (n, 3))
        if beacon_hz:
            tt = np.arange(n) / self.fs
            acc += np.outer(np.sin(2 * np.pi * beacon_hz * tt), _unit([0.3, 0.3, 0.9])) * 0.01
        gyr = self.rng.normal(0, 0.15, (n, 3)) + np.array([0.4, -0.3, 0.2])
        t0 = self.t
        self._emit(n, acc, gyr, np.tile([self.x, self.y], (n, 1)), np.full(n, self.level))
        self.g_now = gu
        self.truth["rests"].append({"start": t0, "end": self.t, "label": label, "kind": kind,
                                    "x": self.x, "y": self.y, "gravity": list(gu)})

    def hand_hold(self, secs=12.0):
        n = self._n(secs)
        tt = np.arange(n) / self.fs
        u = self.u_walk
        f = self.rng.uniform(7, 10)
        trem = np.column_stack([np.sin(2 * np.pi * f * tt + p) for p in self.rng.uniform(0, 6, 3)]) * 0.007
        sway = np.column_stack([np.sin(2 * np.pi * 0.4 * tt + p) for p in self.rng.uniform(0, 6, 3)]) * 0.003
        acc = u + trem + sway + self.rng.normal(0, 0.002, (n, 3))
        gyr = np.column_stack([np.sin(2 * np.pi * f * tt + p) for p in self.rng.uniform(0, 6, 3)]) * 1.0
        gyr += self.rng.normal(0, 0.2, (n, 3))
        self.transition(u, 0.8)
        t0 = self.t
        self._emit(n, acc, gyr, np.tile([self.x, self.y], (n, 1)), np.full(n, self.level))
        self.truth["hand_held"].append({"start": t0, "end": self.t, "x": self.x, "y": self.y})

    def taps(self, count):
        """Tap the sensor count times while it sits in its rest pose."""
        spacing = 0.35
        secs = count * spacing + 0.8
        n = self._n(secs)
        gu = np.array(self.g_now)
        acc = gu + self.rng.normal(0, 0.01, (n, 3))
        times = []
        for k in range(count):
            i = int((0.3 + k * spacing) * self.fs)
            acc[i] += gu * 6.0
            if i + 1 < n:
                acc[i + 1] -= gu * 2.0
            times.append(self.t + i / self.fs)
        gyr = self.rng.normal(0, 1.0, (n, 3))
        self._emit(n, acc, gyr, np.tile([self.x, self.y], (n, 1)), np.full(n, self.level))
        self.truth["taps"].append({"count": count, "times": times})

    def walk_to(self, tx, ty, via: list | None = None, level: float | None = None):
        self.transition(self.u_walk, 1.0)
        pts = [(self.x, self.y)] + list(via or []) + [(tx, ty)]
        P = np.array(pts, float)
        seg = np.hypot(*np.diff(P, axis=0).T)
        L = seg.sum()
        if L < 0.5:
            return
        o = self.o
        speed = o.speed_mps * self.rng.uniform(0.95, 1.05)
        secs = L / speed
        n = self._n(secs)
        tt = np.arange(n) / self.fs
        s = np.linspace(0, L, n)
        cs = np.concatenate([[0], np.cumsum(seg)])
        x = np.interp(s, cs, P[:, 0])
        y = np.interp(s, cs, P[:, 1])
        # Heading follows segments; turns are smoothed over about 1.5 s
        head_seg = np.arctan2(np.diff(P[:, 1]), np.diff(P[:, 0]))
        idx = np.clip(np.searchsorted(cs, s, side="right") - 1, 0, len(seg) - 1)
        th = np.unwrap(np.concatenate([[self.heading], head_seg]))[1:][idx]
        k = max(int(1.5 * self.fs), 1)
        # Trailing moving average: continuous with the previous heading, so the
        # gyro sees the whole turn at the start of the walk and at each corner.
        th = np.convolve(np.concatenate([np.full(k - 1, self.heading), th]), np.ones(k) / k, mode="valid")
        yaw = np.gradient(th, 1 / self.fs)                     # rad/s CCW about up
        f = o.cadence_hz
        u = self.u_walk
        fwd = _unit(np.cross(u, [1, 0, 0]))
        side = np.cross(u, fwd)
        ph = 2 * np.pi * f * tt
        acc = (u[None, :] * (1 + 0.22 * np.sin(ph))[:, None]
               + fwd[None, :] * (0.08 * np.sin(ph + 1.2))[:, None]
               + side[None, :] * (0.05 * np.sin(ph / 2))[:, None]
               + self.rng.normal(0, 0.02, (n, 3)))
        gyr = u[None, :] * np.degrees(yaw)[:, None] + self.rng.normal(0, 0.4, (n, 3)) + np.array([0.4, -0.3, 0.2])
        gyr += np.column_stack([np.sin(ph + p) for p in (0, 1, 2)]) * 2.0   # body sway
        alt = np.full(n, self.level)
        if level is not None and level != self.level:
            # take the stairs in the middle third of the leg
            a, b = n // 3, 2 * n // 3
            alt[a:b] = np.linspace(self.level, level, b - a)
            alt[b:] = level
            self.level = level
        self._emit(n, acc, gyr, np.column_stack([x, y]), alt)
        self.truth["steps"] += int(round(secs * f))
        self.x, self.y = float(tx), float(ty)
        self.heading = float(th[-1])
        self.g_now = u

    def handle(self, secs=4.0):
        """Staff handling: random motion before START or after FINISH."""
        n = self._n(secs)
        acc = self.u_walk + self.rng.normal(0, 0.25, (n, 3))
        gyr = self.rng.normal(0, 25, (n, 3))
        self._emit(n, acc, gyr, np.tile([self.x, self.y], (n, 1)), np.full(n, self.level))
        self.g_now = self.u_walk

    # -- output -------------------------------------------------------------
    def write(self, out_dir: Path, extra_truth: dict | None = None) -> Path:
        o = self.o
        out = Path(out_dir)
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        t = np.concatenate(self.ts)
        A = np.vstack(self.acc)
        G = np.vstack(self.gyr)
        XY = np.vstack(self.pos)
        ALT = np.concatenate(self.alt)
        rng = self.rng

        B.write_channel(out, 80, t, {"x": A[:, 0], "y": A[:, 1], "z": A[:, 2]})
        tg = np.arange(0, t[-1], 1 / o.gyro_hz)
        B.write_channel(out, 47, tg, {k: np.interp(tg, t, G[:, i]) for i, k in enumerate("xyz")})
        te = np.arange(0, t[-1], 0.1)
        xe, ye, ae = (np.interp(te, t, v) for v in (XY[:, 0], XY[:, 1], ALT))
        pres = 101325 - 12.0 * ae + rng.normal(0, 1.5, len(te))
        temp = 21.5 + 0.03 * xe - 0.015 * ye + rng.normal(0, 0.05, len(te))
        hum = 42 + 0.04 * ye + rng.normal(0, 0.2, len(te))
        B.write_channel(out, 20, te, {"pressure": pres, "temperature": temp, "humidity": hum})
        tl = np.arange(0, t[-1], 0.25)
        xl, yl = np.interp(tl, t, XY[:, 0]), np.interp(tl, t, XY[:, 1])
        lux = 350 + 250 * np.sin(xl / 25) * np.cos(yl / 30) + rng.normal(0, 10, len(tl))
        B.write_channel(out, 76, tl, {"lux": np.maximum(lux, 0), "uv": np.zeros(len(tl))})

        roles = {"accel": 80, "hf_accel": None, "gyro": 47, "env": 20, "env2": None, "light": 76, "gps": None}
        gps_fields = []
        frame = LocalFrame(*self.c.origin)
        if o.gps_profile != "none":
            gdf = synth_gps(t, XY, frame, o.gps_profile, rng)
            if len(gdf):
                B.write_gps(out, gdf)
                roles["gps"] = ["synthetic"]
                gps_fields = [c for c in gdf.columns if c != "t"]

        channels = [
            _ch(80, "40g DC Acceleration", o.accel_hz, "ACCELERATION", ["x", "y", "z"], "g", len(t)),
            _ch(47, "IMU Rotation", o.gyro_hz, "ROTATION", ["x", "y", "z"], "dps", len(tg)),
            {"id": 20, "name": "Internal Pressure/Temperature/Humidity", "rate_hz": 10.0, "n": len(te),
             "file": "ch_20.parquet", "subchannels": [
                 {"name": "Pressure", "units": "Pa", "measurement": "PRESSURE", "column": "pressure"},
                 {"name": "Temperature", "units": "°C", "measurement": "TEMPERATURE", "column": "temperature"},
                 {"name": "Relative Humidity", "units": "RH", "measurement": "HUMIDITY", "column": "humidity"}]},
            {"id": 76, "name": "Light Sensor", "rate_hz": 4.0, "n": len(tl), "file": "ch_76.parquet",
             "subchannels": [{"name": "Lux", "units": "lux", "measurement": "LIGHT", "column": "lux"},
                             {"name": "UV", "units": "index", "measurement": "LIGHT", "column": "uv"}]},
        ]
        step = max(int(self.fs / 2), 1)
        truth = {
            "kind": o.kind, "gps_profile": o.gps_profile, "options": o.__dict__.copy(),
            "course": self.c.to_dict(), **{k: v for k, v in self.truth.items() if k != "path"},
            "path": {"t": t[::step].round(2).tolist(), "x": XY[::step, 0].round(2).tolist(),
                     "y": XY[::step, 1].round(2).tolist()},
            **(extra_truth or {}),
        }
        (out / "ground_truth.json").write_text(json.dumps(truth, default=_json))
        B.write_meta(out, {
            "source": {"file": out.name + ".synth.zip", "size": None, "sha256": f"synthetic-{out.name}-{o.seed}"},
            "device": {"serial": o.serial, "model": "SYNTHETIC-GPS", "firmware": "synthetic",
                       "recorder_name": f"Synthetic {o.kind}", "calibration_expiry": None,
                       "calibration_expired": None},
            "start_epoch": o.start_epoch,
            "start_utc": pd.Timestamp(o.start_epoch, unit="s", tz="UTC").isoformat(),
            "duration_s": float(t[-1]),
            "channels": channels, "roles": roles, "gps_fields": gps_fields, "synthetic": True,
        })
        return out


def _ch(i, name, rate, mt, cols, units, n):
    return {"id": i, "name": name, "rate_hz": rate, "n": n, "file": f"ch_{i}.parquet",
            "subchannels": [{"name": c.upper(), "units": units, "measurement": mt, "column": c} for c in cols]}


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def _json(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


GPS_PROFILES = {
    "outdoor": {"sigma": 2.5, "tau": 25, "white": 1.0, "hdop": (0.8, 1.4), "sats": (9, 13), "acc": (3.2, 4.8), "drop": 0.0},
    "indoor": {"sigma": 14.0, "tau": 60, "white": 4.0, "hdop": (2.0, 4.8), "sats": (4, 8), "acc": (18, 26), "drop": 0.15},
    "dropout": {"sigma": 4.0, "tau": 30, "white": 1.5, "hdop": (1.2, 2.5), "sats": (5, 9), "acc": (5.5, 7.5), "drop": 0.62},
}


def synth_gps(t, XY, frame: LocalFrame, profile: str, rng) -> pd.DataFrame:
    p = GPS_PROFILES[profile]
    tg = np.arange(np.ceil(t[0]), t[-1], 1.0)
    x = np.interp(tg, t, XY[:, 0])
    y = np.interp(tg, t, XY[:, 1])
    n = len(tg)
    a = np.exp(-1.0 / p["tau"])
    e = np.zeros((n, 2))
    e[0] = rng.normal(0, p["sigma"], 2)
    for i in range(1, n):
        e[i] = a * e[i - 1] + np.sqrt(1 - a * a) * rng.normal(0, p["sigma"], 2)
    e += rng.normal(0, p["white"], (n, 2))
    # Dropouts come in long stretches (Markov on/off)
    have = np.ones(n, bool)
    if p["drop"] > 0:
        state, i = True, 0
        mean_on = 60 * (1 - p["drop"]) / max(p["drop"], 1e-3)
        while i < n:
            dur = int(rng.exponential(mean_on if state else 60)) + 5
            have[i:i + dur] = state
            i += dur
            state = not state
    lat, lon = frame.to_latlon(x + e[:, 0], y + e[:, 1])
    df = pd.DataFrame({
        "t": tg, "lat": lat, "lon": lon,
        "alt": 620 + rng.normal(0, 3 if profile == "outdoor" else 10, n),
        "speed": np.abs(np.gradient(np.hypot(np.gradient(x), np.gradient(y)))) + np.hypot(np.gradient(x), np.gradient(y)),
        "fix": np.where(have, 3, 0).astype(float),
        "sats": rng.integers(*p["sats"], n).astype(float),
        "hdop": rng.uniform(*p["hdop"], n),
        "acc": rng.uniform(*p["acc"], n),
        "gps_time": 1790000000.0 + tg,
    })
    return df[have].reset_index(drop=True)


# -- scenarios ----------------------------------------------------------------

def survey(course: SynthCourse, o: Opts, order: list[int] | None = None) -> Gen:
    o.kind = "survey"
    g = Gen(course, o)
    order = order or [s["number"] for s in course.stations]
    g.handle(4)
    _place(g, 0, 15.0, o)
    for n in order:
        st = course.point(n)
        g.walk_to(st["x"], st["y"], via=_via(g, st), level=4.0 if n in course.mezzanine else 0.0)
        _place(g, n, g.rng.uniform(15, 20), o)
        g.truth["visits"].append(n)
    g.walk_to(course.booth["x"], course.booth["y"], via=_via(g, course.booth), level=0.0)
    _place(g, 0, 15.0, o, finish=True)
    g.handle(3)
    return g


def participant(course: SynthCourse, o: Opts, order: list[int], strays: int = 1,
                hand_holds: int = 1, rest_s: float = 10.5) -> Gen:
    o.kind = "participant"
    g = Gen(course, o)
    g.handle(5)
    _place(g, 0, rest_s + 1, o)
    stray_after = set(g.rng.choice(len(order), size=min(strays, len(order)), replace=False).tolist()) if strays else set()
    hold_after = set(g.rng.choice(len(order), size=min(hand_holds, len(order)), replace=False).tolist()) if hand_holds else set()
    for i, n in enumerate(order):
        st = course.point(n)
        g.walk_to(st["x"], st["y"], via=_via(g, st), level=4.0 if n in course.mezzanine else 0.0)
        _place(g, n, rest_s + g.rng.uniform(0, 3), o)
        g.truth["visits"].append(n)
        if i in hold_after:
            g.walk_to(g.x + g.rng.uniform(-6, 6), g.y + g.rng.uniform(-6, 6))
            g.hand_hold(12.0)
        if i in stray_after:
            sx, sy = _stray_point(course, g.rng)
            g.walk_to(sx, sy)
            g.transition(FACE_UP)
            g.rest(FACE_UP, rest_s + 1, label="stray", kind="stray")
            g.truth["strays"].append({"x": sx, "y": sy, "t": g.t})
    g.walk_to(course.booth["x"], course.booth["y"], via=_via(g, course.booth), level=0.0)
    _place(g, 0, rest_s + 1, o, finish=True)
    g.handle(3)
    return g


def _place(g: Gen, n: int, secs: float, o: Opts, finish: bool = False):
    st = g.c.point(n)
    pose = st["holder"] if (o.use_holders or n == 0 and o.use_holders) else _natural_pose(g, n)
    g.transition(pose)
    if o.use_taps and n > 0:
        g.taps(st["tap_count"])
    g.rest(pose, secs, label="FINISH" if finish else ("START" if n == 0 else n),
           beacon_hz=st.get("beacon_hz") if o.use_beacons and n > 0 else None,
           kind="booth" if n == 0 else "station")


def _natural_pose(g: Gen, n: int):
    # With GPS only, people set the sensor down however: mostly face up, sometimes on a side
    return FACE_UP if g.rng.random() < 0.7 else HOLDERS[g.rng.integers(0, 4)]


def _via(g: Gen, target: dict):
    """An aisle-style corner between points, so routes are not straight lines."""
    if g.rng.random() < 0.5:
        return [(target["x"], g.y)]
    return [(g.x, target["y"])]


def _stray_point(course: SynthCourse, rng):
    pts = [(s["x"], s["y"]) for s in course.stations] + [(course.booth["x"], course.booth["y"])]
    for _ in range(200):
        x, y = rng.uniform(-30, 75), rng.uniform(-10, 95)
        if min(np.hypot(x - a, y - b) for a, b in pts) > 25:
            return float(x), float(y)
    return 60.0, 80.0


def zip_bundle(bdir: Path, zpath: Path | None = None) -> Path:
    zpath = zpath or bdir.with_suffix(".synth.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(bdir.iterdir()):
            z.write(f, f.name)
    return zpath


def unzip_bundle(data: bytes, out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if "/" in name or name.startswith("."):
                continue
            (out / name).write_bytes(z.read(name))
    if not (out / "meta.json").exists():
        raise ValueError("zip is not a recording bundle (meta.json missing)")
    return out
