"""Read an enDAQ .IDE file with idelib/endaq and write a normalized bundle."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import shutil
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import get_config
from . import bundle as B
from . import ide_stream as S
from . import reduce as R
from .channel_discovery import (ChannelInfo, SubInfo, assign_roles, column_name,
                                measurement_type)

log = logging.getLogger(__name__)


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def open_doc(path: str | Path):
    import endaq.ide
    return endaq.ide.get_doc(str(path))


def _units(sub) -> str:
    u = getattr(sub, "units", None)
    if isinstance(u, (tuple, list)):
        return str(u[1] if len(u) > 1 and u[1] else (u[0] if u else ""))
    return str(u or "")


def _channel_arrays(ch) -> tuple[np.ndarray, np.ndarray]:
    """Return (t_us, values[nsub, n]) for an idelib channel."""
    ea = ch.getSession()
    try:
        arr = ea.arraySlice()
        t = np.asarray(arr[0], dtype=np.float64)
        vals = np.asarray(arr[1:], dtype=np.float64)
        return t, vals
    except Exception:
        import endaq.ide
        df = endaq.ide.to_pandas(ch, time_mode="seconds")
        t = np.asarray(df.index, dtype=np.float64) * 1e6
        return t, df.to_numpy(dtype=np.float64).T


def _count(ch) -> int:
    try:
        return len(ch.getSession())
    except Exception:
        return 0


def discover(doc) -> list[ChannelInfo]:
    chans = []
    for cid, ch in sorted(doc.channels.items()):
        subs = []
        mtypes = [measurement_type(s) for s in ch.subchannels]
        for i, s in enumerate(ch.subchannels):
            name = str(getattr(s, "name", f"s{i}"))
            units = _units(s)
            col = column_name(name, units, mtypes[i], i)
            subs.append(SubInfo(i, name, units, mtypes[i], col))
        _dedupe_columns(subs)
        try:
            rate = S.rate_hz(ch.getSession())      # from block timing; no samples are read
        except Exception:
            rate = 0.0
        chans.append(ChannelInfo(int(cid), str(ch.name), float(rate), subs))
    return chans


def _dedupe_columns(subs: list[SubInfo]) -> None:
    seen: dict[str, int] = {}
    for s in subs:
        if s.column in seen:
            seen[s.column] += 1
            s.column = f"{s.column}_{seen[s.column]}"
        else:
            seen[s.column] = 0


def device_info(doc) -> dict:
    ri = dict(getattr(doc, "recorderInfo", {}) or {})

    def g(*keys):
        for k in keys:
            if ri.get(k) not in (None, ""):
                return ri[k]
        return None

    cal_exp = g("CalibrationExpiry", "CalibrationExpirationDate")
    if isinstance(cal_exp, (int, float)) and cal_exp > 0:
        cal_exp = dt.datetime.fromtimestamp(cal_exp, dt.timezone.utc).date().isoformat()
    fw = g("FwRevStr", "FwRev")
    return {
        "serial": g("RecorderSerial", "SerialNumber"),
        "model": g("PartNumber", "ProductName"),
        "firmware": str(fw) if fw is not None else None,
        "recorder_name": g("UserDeviceName", "RecorderName"),
        "hardware": g("HwRev"),
        "calibration_expiry": cal_exp,
        "calibration_expired": _cal_expired(cal_exp),
    }


def _cal_expired(cal_exp) -> bool | None:
    if not cal_exp:
        return None
    try:
        return dt.date.fromisoformat(str(cal_exp)[:10]) < dt.date.today()
    except ValueError:
        return None


def session_start(doc) -> float | None:
    for attr in ("lastSession",):
        s = getattr(doc, attr, None)
        if s is not None and getattr(s, "utcStartTime", None):
            return float(s.utcStartTime)
    sessions = getattr(doc, "sessions", None) or []
    for s in sessions:
        if getattr(s, "utcStartTime", None):
            return float(s.utcStartTime)
    return None


def ide_to_bundle(src: str | Path, out_dir: str | Path, *, file_hash: str | None = None,
                  progress=None) -> B.Bundle:
    """Parse src .IDE into out_dir. Returns the bundle. Long recordings are read in
    slices (see reduce.py); progress(fraction) is called while they are read."""
    t_start = time.time()
    src = Path(src)
    out = Path(out_dir)
    tmp = out.with_name(out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    cfg = get_config()
    lc = cfg.large_recordings
    streamed = src.stat().st_size > lc.stream_file_mb * 2**20
    if streamed:                     # big file: keep only block metadata in memory (ide_stream.py)
        doc, _ = S.open_streaming(src, lc.max_rows_per_channel,
                                  progress=(lambda f: progress(0.15 * f)) if progress else None)
    else:
        doc = open_doc(src)
    chans = discover(doc)
    roles = assign_roles(chans)

    counts = {c.id: _count(doc.channels[c.id]) for c in chans}
    factors = R.plan(counts, cfg, force=streamed)
    raw: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for c in chans:
        if not factors or factors[c.id] == 1:
            raw[c.id] = _channel_arrays(doc.channels[c.id])
    firsts = [v[0][0] for v in raw.values() if len(v[0])]
    if factors:
        firsts += [S.first_time(doc.channels[c.id].getSession())
                   for c in chans if factors[c.id] > 1 and counts[c.id]]
    t0_us = min(firsts) if firsts else 0.0

    ch_meta = []
    t_end = 0.0
    done, total = 0, max(sum(counts.values()), 1)
    p0 = 0.15 if streamed else 0.0

    def report(f):
        if progress:
            progress(p0 + (1 - p0) * f)
    stat_ids = {roles.get("accel"), roles.get("hf_accel")}
    for c in chans:
        d = c.to_dict()
        if c.id in raw:
            t_us, vals = raw[c.id]
            t = (t_us - t0_us) / 1e6
            cols = {s.column: vals[s.index] for s in c.subs if s.index < len(vals)}
            n = B.write_channel(tmp, c.id, t, cols)
            if n:
                t_end = max(t_end, float(t[-1]))
        else:
            k = factors[c.id]
            colnames = [(s.index, s.column) for s in c.subs]
            stats = c.id in stat_ids and len(c.subs) >= 3 and [s.column for s in c.subs[:3]] == ["x", "y", "z"]
            base = done
            df, n_src = R.stream_channel(
                S.BlockReader(doc.channels[c.id].getSession()), colnames, k, t0_us, tmp, c.id, c.rate_hz, cfg, stats,
                progress=lambda f, base=base, n=counts[c.id]: report((base + f * n) / total))
            df.to_parquet(tmp / f"ch_{c.id}.parquet", index=False)
            n = len(df)
            if n:
                t_end = max(t_end, float(df["t"].iloc[-1]))
            d.update(rate_hz=round(c.rate_hz / k, 3), source_rate_hz=round(c.rate_hz, 3), source_n=n_src,
                     decimation=k, full_rate_stats=bool(stats))
        done += counts[c.id]
        report(done / total)
        d["n"] = n
        d["file"] = f"ch_{c.id}.parquet"
        ch_meta.append(d)

    gps_fields: list[str] = []
    if roles.get("gps"):
        gdf = _merge_gps(chans, raw, roles["gps"], t0_us)
        if gdf is not None and len(gdf):
            B.write_gps(tmp, gdf)
            gps_fields = [c for c in gdf.columns if c != "t"]
        else:
            roles["gps"] = None

    start = session_start(doc)
    meta = {
        "source": {
            "file": src.name,
            "size": src.stat().st_size,
            "sha256": file_hash or sha256_file(src),
        },
        "device": device_info(doc),
        "start_epoch": start,
        "start_utc": dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat() if start else None,
        "duration_s": round(t_end, 3),
        "channels": ch_meta,
        "roles": roles,
        "gps_fields": gps_fields,
        "synthetic": False,
        "reduced": bool(factors),
        "parse_seconds": round(time.time() - t_start, 2),
    }
    B.write_meta(tmp, meta)
    try:
        doc.close()
    except Exception:
        pass
    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    return B.open_bundle(out)


def _merge_gps(chans, raw, gps_ids, t0_us) -> pd.DataFrame | None:
    """Combine every GPS-related subchannel into one table on the lat/lon timebase."""
    frames = []
    for c in chans:
        if c.id not in gps_ids or c.id not in raw:
            continue
        t_us, vals = raw[c.id]
        df = pd.DataFrame({"t": (t_us - t0_us) / 1e6})
        for s in c.subs:
            if s.column in ("lat", "lon", "alt", "speed", "heading", "hdop", "sats",
                            "fix", "acc", "gps_time") and s.index < len(vals):
                df[s.column] = vals[s.index]
        if len(df.columns) > 1:
            frames.append(df.sort_values("t"))
    base = next((f for f in frames if {"lat", "lon"} <= set(f.columns)), None)
    if base is None:
        return None
    for f in frames:
        if f is base:
            continue
        extra = [c for c in f.columns if c != "t" and c not in base.columns]
        if extra:
            base = pd.merge_asof(base, f[["t"] + extra], on="t", direction="nearest",
                                 tolerance=2.0)
    # Drop null-island and invalid positions
    ok = base["lat"].between(-90, 90) & base["lon"].between(-180, 180)
    ok &= ~((base["lat"].abs() < 1e-6) & (base["lon"].abs() < 1e-6))
    return base[ok].reset_index(drop=True)
