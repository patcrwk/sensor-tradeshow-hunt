"""Find channels by what they measure, not by channel number.

Uses the measurement types endaq.ide assigns to each subchannel (ACCELERATION,
ROTATION, PRESSURE, LOCATION, SPEED, DIRECTION, ...). Falls back to units and
names when a type is missing. GPS is discovered at runtime: any subchannel of
type LOCATION/SPEED/DIRECTION, or on a channel whose name mentions GPS/GNSS.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:  # endaq is the source of truth for measurement types
    from endaq.ide import measurement as _m
except Exception:  # pragma: no cover
    _m = None


@dataclass
class SubInfo:
    index: int
    name: str
    units: str
    mtype: str          # upper-case measurement type key, e.g. "ACCELERATION"
    column: str         # normalized column name


@dataclass
class ChannelInfo:
    id: int
    name: str
    rate_hz: float
    subs: list[SubInfo] = field(default_factory=list)

    @property
    def mtypes(self) -> set[str]:
        return {s.mtype for s in self.subs}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "rate_hz": round(self.rate_hz, 3),
            "subchannels": [
                {"name": s.name, "units": s.units, "measurement": s.mtype, "column": s.column}
                for s in self.subs
            ],
        }


GPS_KEYWORDS = re.compile(r"gps|gnss|location|position", re.I)


def measurement_type(subchannel) -> str:
    """Return upper-case measurement type key for an idelib subchannel."""
    if _m is not None:
        try:
            mt = _m.get_measurement_type(subchannel)
            for const in _CONSTS:
                if mt is getattr(_m, const, object()) or (mt is not None and mt == getattr(_m, const, None)):
                    return _canonical(const)
        except Exception:
            pass
    return _guess_type(getattr(subchannel, "name", ""), _units_of(subchannel))


# endaq.ide.measurement constants we care about, most specific first
_CONSTS = ["LOCATION", "SPEED", "DIRECTION", "ACCELERATION", "ROTATION", "GYRO", "ANG_RATE",
           "PRESSURE", "TEMPERATURE", "HUMIDITY", "LIGHT", "ALTITUDE", "TIME", "MAGNETIC",
           "ORIENTATION", "QUATERNION", "VOLTAGE", "AUDIO"]


def _canonical(key: str) -> str:
    aliases = {"ACCEL": "ACCELERATION", "GYRO": "ROTATION", "ANG_RATE": "ROTATION", "ROT": "ROTATION",
               "TEMP": "TEMPERATURE", "PRES": "PRESSURE", "HUMIDITY": "HUMIDITY",
               "LOC": "LOCATION", "GPS": "LOCATION", "LUX": "LIGHT"}
    for a, full in aliases.items():
        if key == a or key.startswith(a + "_"):
            return full
    return key


def _units_of(sub) -> str:
    u = getattr(sub, "units", None)
    if isinstance(u, (tuple, list)):
        return str(u[1] if len(u) > 1 and u[1] else u[0] if u else "")
    return str(u or "")


def _guess_type(name: str, units: str) -> str:
    n, u = name.lower(), units.lower()
    if "lat" in n or "lon" in n or GPS_KEYWORDS.search(n):
        if "speed" in n or "velocity" in n:
            return "SPEED"
        if "heading" in n or "course" in n or "direction" in n:
            return "DIRECTION"
        return "LOCATION"
    if u in ("g", "m/s²", "m/s^2") or "accel" in n:
        return "ACCELERATION"
    if u in ("dps", "deg/s", "°/s", "rad/s") or "rot" in n or "gyro" in n:
        return "ROTATION"
    if u in ("pa", "kpa", "hpa", "mbar") or "press" in n:
        return "PRESSURE"
    if u in ("°c", "degc", "c") or "temp" in n:
        return "TEMPERATURE"
    if "humid" in n or u in ("%rh", "rh"):
        return "HUMIDITY"
    if "lux" in n or u == "lux" or "light" in n:
        return "LIGHT"
    if "uv" in n:
        return "LIGHT"
    return "UNKNOWN"


def column_name(sub_name: str, units: str, mtype: str, idx: int) -> str:
    n = sub_name.lower().strip()
    if mtype in ("ACCELERATION", "ROTATION"):
        for ax in ("x", "y", "z"):
            if n == ax or n.endswith(" " + ax) or n.startswith(ax + " ") or n.endswith("(" + ax + ")"):
                return ax
        return ["x", "y", "z", "w"][idx] if idx < 4 else f"s{idx}"
    if mtype == "PRESSURE":
        return "pressure"
    if mtype == "TEMPERATURE":
        return "temperature"
    if mtype == "HUMIDITY":
        return "humidity"
    if mtype == "LIGHT":
        return "uv" if "uv" in n else "lux"
    if mtype in ("LOCATION", "SPEED", "DIRECTION") or GPS_KEYWORDS.search(n):
        return gps_column(n, mtype) or f"s{idx}"
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_") or f"s{idx}"


def gps_column(n: str, mtype: str = "") -> str | None:
    n = n.lower()
    if "lat" in n:
        return "lat"
    if "lon" in n:
        return "lon"
    if "alt" in n or "height" in n or "elev" in n:
        return "alt"
    if "speed" in n or "velocity" in n or mtype == "SPEED":
        return "speed"
    if "heading" in n or "course" in n or "direction" in n or mtype == "DIRECTION":
        return "heading"
    if "hdop" in n or "dop" in n:
        return "hdop"
    if "sat" in n:
        return "sats"
    if "fix" in n or "quality" in n:
        return "fix"
    if "acc" in n or "error" in n or "uncert" in n:
        return "acc"
    if "time" in n or "epoch" in n or "utc" in n:
        return "gps_time"
    return None


def assign_roles(channels: list[ChannelInfo]) -> dict:
    """Pick the channel for each role. Returns {role: channel id or None}."""

    def acc_channels():
        return [c for c in channels if "ACCELERATION" in c.mtypes and len(c.subs) >= 3]

    roles: dict = {"accel": None, "hf_accel": None, "gyro": None, "env": None,
                   "env2": None, "light": None, "gps": None}
    accs = acc_channels()
    if accs:
        # DC accelerometer: prefer names with "DC"; else the lowest-rate triaxial one.
        dc = [c for c in accs if re.search(r"\bdc\b", c.name, re.I)]
        pe = [c for c in accs if re.search(r"\bpe\b|piezo", c.name, re.I)]
        roles["accel"] = (dc or sorted(accs, key=lambda c: c.rate_hz))[0].id
        rest = [c for c in accs if c.id != roles["accel"]]
        if pe or rest:
            roles["hf_accel"] = (pe or sorted(rest, key=lambda c: -c.rate_hz))[0].id
    gyros = [c for c in channels if "ROTATION" in c.mtypes and len(c.subs) >= 3]
    if gyros:
        # For walking we want a modest-rate IMU; prefer channels near 100-400 Hz.
        roles["gyro"] = sorted(gyros, key=lambda c: abs(c.rate_hz - 200))[0].id
        roles["gyro_hf"] = sorted(gyros, key=lambda c: -c.rate_hz)[0].id
    envs = [c for c in channels if "PRESSURE" in c.mtypes]
    if envs:
        internal = [c for c in envs if re.search(r"internal", c.name, re.I)]
        ordered = internal + [c for c in envs if c not in internal]
        roles["env"] = ordered[0].id
        if len(ordered) > 1:
            roles["env2"] = ordered[1].id
    lights = [c for c in channels if "LIGHT" in c.mtypes]
    if lights:
        roles["light"] = lights[0].id
    gps = gps_channels(channels)
    if gps:
        roles["gps"] = [c.id for c in gps]
    return roles


def gps_channels(channels: list[ChannelInfo]) -> list[ChannelInfo]:
    out = []
    for c in channels:
        if c.mtypes & {"LOCATION", "SPEED", "DIRECTION"} or GPS_KEYWORDS.search(c.name):
            out.append(c)
    # A location channel must carry lat and lon somewhere.
    cols = {s.column for c in out for s in c.subs}
    if not {"lat", "lon"} <= cols:
        return []
    return out


def describe(channels: list[ChannelInfo], roles: dict) -> str:
    lines = []
    for c in channels:
        subs = ", ".join(f"{s.name} [{s.units}] {s.mtype}->{s.column}" for s in c.subs)
        lines.append(f"  ch {c.id:>3}  {c.name:<45} {c.rate_hz:9.1f} Hz  {subs}")
    lines.append("  roles: " + ", ".join(f"{k}={v}" for k, v in roles.items()))
    lines.append("  location channel: " + ("FOUND " + str(roles.get('gps')) if roles.get("gps") else "none"))
    return "\n".join(lines)
