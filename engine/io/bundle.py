"""The normalized recording bundle.

Every recording (real .IDE or synthetic) becomes a directory:

    meta.json                 device, session, channel inventory, roles
    ch_<id>.parquet           one table per channel: column "t" (seconds from
                              recording start, float64) plus one column per
                              subchannel, float32
    gps.parquet               optional, merged GPS stream with normalized columns
                              t, lat, lon and optional alt, speed, fix, sats,
                              hdop, acc, gps_time
    ground_truth.json         optional, synthetic files only
    env_<id>.parquet          long recordings only: min/max envelope of an
                              averaged channel (columns <col>__min, <col>__max)
    full_<id>.json / .npz     long recordings only: statistics measured on the
                              full-rate data (see io/reduce.py)

Roles map a purpose to a channel id so the detectors never depend on
specific enDAQ channel numbers:
    accel     low-rate DC accelerometer, columns x, y, z in g
    hf_accel  high-rate accelerometer (piezo), columns x, y, z in g
    gyro      rotation rate, columns x, y, z in deg/s
    env       pressure (Pa), temperature (C), humidity (%RH)
    light     lux, uv
    gps       special: gps.parquet
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

FORMAT = "endaq-demo-bundle/1"


@dataclass
class Bundle:
    path: Path
    _cache: dict = field(default_factory=dict, repr=False)

    @cached_property
    def meta(self) -> dict:
        return json.loads((self.path / "meta.json").read_text())

    @property
    def roles(self) -> dict:
        return self.meta.get("roles", {})

    @property
    def has_gps(self) -> bool:
        return (self.path / "gps.parquet").exists()

    @property
    def duration_s(self) -> float:
        return float(self.meta.get("duration_s", 0.0))

    def channel_info(self, ch_id) -> dict | None:
        for c in self.meta["channels"]:
            if str(c["id"]) == str(ch_id):
                return c
        return None

    def channel(self, ch_id) -> pd.DataFrame:
        key = f"ch_{ch_id}"
        if key not in self._cache:
            self._cache[key] = pd.read_parquet(self.path / f"ch_{ch_id}.parquet")
        return self._cache[key]

    def role(self, name: str) -> pd.DataFrame | None:
        if name == "gps":
            return self.gps()
        ch = self.roles.get(name)
        if ch is None:
            return None
        return self.channel(ch)

    def role_rate(self, name: str) -> float | None:
        ch = self.roles.get(name)
        info = self.channel_info(ch) if ch is not None else None
        return info.get("rate_hz") if info else None

    def gps(self) -> pd.DataFrame | None:
        if not self.has_gps:
            return None
        if "gps" not in self._cache:
            self._cache["gps"] = pd.read_parquet(self.path / "gps.parquet")
        return self._cache["gps"]

    @property
    def reduced(self) -> bool:
        return bool(self.meta.get("reduced"))

    def envelope(self, ch_id) -> pd.DataFrame | None:
        p = self.path / f"env_{ch_id}.parquet"
        if not p.exists():
            return None
        key = f"env_{ch_id}"
        if key not in self._cache:
            self._cache[key] = pd.read_parquet(p)
        return self._cache[key]

    def fullrate(self, ch_id) -> dict | None:
        """Full-rate statistics of a channel that was averaged down, or None."""
        if ch_id is None:
            return None
        p = self.path / f"full_{ch_id}.json"
        if not p.exists():
            return None
        key = f"full_{ch_id}"
        if key not in self._cache:
            self._cache[key] = json.loads(p.read_text())
        return self._cache[key]

    def peak_windows(self, ch_id) -> list[pd.DataFrame]:
        """Full-rate x/y/z around each fullrate() event, indexed by time."""
        p = self.path / f"full_{ch_id}.npz"
        if not p.exists():
            return []
        z = np.load(p)
        out = []
        for i in range(len(self.fullrate(ch_id).get("events", []))):
            if f"t{i}" in z:
                out.append(pd.DataFrame(z[f"x{i}"].astype(np.float64), index=pd.Index(z[f"t{i}"], name="t"),
                                        columns=["x", "y", "z"]))
        return out

    def vibration(self, role: str) -> dict | None:
        """Band-limited vibration RMS (10 Hz) measured at full rate, when available."""
        fr = self.fullrate(self.roles.get(role))
        return fr.get("vibration") if fr else None

    def ground_truth(self) -> dict | None:
        p = self.path / "ground_truth.json"
        return json.loads(p.read_text()) if p.exists() else None


def write_channel(path: Path, ch_id, t: np.ndarray, cols: dict[str, np.ndarray]) -> int:
    df = pd.DataFrame({"t": np.asarray(t, dtype=np.float64)})
    for k, v in cols.items():
        df[k] = np.asarray(v, dtype=np.float32)
    df.to_parquet(path / f"ch_{ch_id}.parquet", index=False)
    return len(df)


def write_gps(path: Path, df: pd.DataFrame) -> None:
    df = df.copy()
    df["t"] = df["t"].astype(np.float64)
    for c in ("lat", "lon"):
        df[c] = df[c].astype(np.float64)
    df.to_parquet(path / "gps.parquet", index=False)


def write_meta(path: Path, meta: dict) -> None:
    meta = {"format": FORMAT, **meta}
    (path / "meta.json").write_text(json.dumps(meta, indent=2, default=str))


def open_bundle(path: str | Path) -> Bundle:
    return Bundle(Path(path))
