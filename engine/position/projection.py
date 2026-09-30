"""Local equirectangular projection: lat/lon to east/north meters from an origin.

At venue scale (under a few km) the error is far below GPS error, so there is
no need for pyproj.
"""
from __future__ import annotations

import math

import numpy as np

R_EARTH = 6_371_008.8


class LocalFrame:
    def __init__(self, lat0: float, lon0: float):
        self.lat0 = float(lat0)
        self.lon0 = float(lon0)
        self._kx = math.radians(1) * R_EARTH * math.cos(math.radians(self.lat0))
        self._ky = math.radians(1) * R_EARTH

    def to_xy(self, lat, lon):
        lat = np.asarray(lat, float)
        lon = np.asarray(lon, float)
        return (lon - self.lon0) * self._kx, (lat - self.lat0) * self._ky

    def to_latlon(self, x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        return self.lat0 + y / self._ky, self.lon0 + x / self._kx

    def to_dict(self) -> dict:
        return {"lat0": self.lat0, "lon0": self.lon0}

    @classmethod
    def from_dict(cls, d: dict | None):
        if not d or d.get("lat0") is None:
            return None
        return cls(d["lat0"], d["lon0"])


def path_length(x, y) -> float:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 2:
        return 0.0
    return float(np.sum(np.hypot(np.diff(x), np.diff(y))))


def cumdist(x, y) -> np.ndarray:
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 2:
        return np.zeros(len(x))
    return np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
