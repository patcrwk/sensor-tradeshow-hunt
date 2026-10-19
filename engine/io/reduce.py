"""Read a long recording channel by channel in slices, with flat memory use.

Each high-rate channel becomes:
    ch_<id>.parquet      block means, at most max_rows_per_channel rows (charts,
                         replay, motion and the detectors use these)
    env_<id>.parquet     min and max per envelope block, so spikes stay visible
                         in zoomed-out charts
    full_<id>.json       measured on every full-rate sample, slice by slice:
                         Welch PSD, spectrogram columns, top peak events,
                         resultant statistics and band-limited vibration RMS
    full_<id>.npz        a 2 s full-rate window around each top peak (SRS)

Slices are read with padding so filters and peak windows see across slice edges.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal

PEAK_SPACING_S = 5.0
PEAK_HALF_S = 1.0
N_EVENTS = 8
VIB_BAND = (50.0, 500.0)
SPEC_COLS = 160
SPEC_ROWS = 128


def plan(counts: dict[int, int], cfg) -> dict[int, int] | None:
    """Decimation factor per channel, or None when the file is small enough to read whole."""
    lc = cfg.large_recordings
    if sum(counts.values()) <= lc.full_rows_max:
        return None
    return {cid: max(1, math.ceil(n / lc.max_rows_per_channel)) for cid, n in counts.items()}


class FullRate:
    """Statistics of one x/y/z accelerometer channel, accumulated slice by slice."""

    def __init__(self, fs: float, n_total: int, seg: int, nper: int):
        self.fs, self.seg, self.nper = fs, seg, nper
        self.psd_sum: np.ndarray | None = None
        self.psd_w = 0
        self.f: np.ndarray | None = None
        self.spec_t: list[float] = []
        self.spec_cols: list[np.ndarray] = []
        self.cands: list[dict] = []
        self.r_sum = self.r_sq = 0.0
        self.r_n = 0
        self.vib_t: list[np.ndarray] = []
        self.vib_v: list[np.ndarray] = []
        self.vib_w = max(int(round(fs / 10)), 1)
        hi = min(VIB_BAND[1], fs * 0.45)
        self.vib_band = (min(VIB_BAND[0], hi / 4), hi)
        self.sos = signal.butter(3, [self.vib_band[0] / (fs / 2), hi / (fs / 2)], btype="bandpass", output="sos") \
            if fs > 20 else None

    def add(self, t: np.ndarray, X: np.ndarray, c0: int, c1: int) -> None:
        """t, X[n, 3] cover the padded slice; [c0, c1) is the slice proper."""
        tc, Xc = t[c0:c1], X[c0:c1]
        res_all = np.linalg.norm(X, axis=1)
        res = res_all[c0:c1]
        if not len(res):
            return
        self.r_sum += float(res.sum())
        self.r_sq += float((res ** 2).sum())
        self.r_n += len(res)

        # Welch PSD per segment: the segments are the spectrogram columns, their
        # length-weighted mean is the whole-recording PSD
        for s0 in range(0, len(res), self.seg):
            s1 = min(s0 + self.seg, len(res))
            if s1 - s0 < self.nper:
                continue
            seg4 = np.column_stack([Xc[s0:s1], res[s0:s1]])
            f, P = signal.welch(seg4, fs=self.fs, nperseg=self.nper, axis=0, scaling="density")
            if self.psd_sum is None:
                self.psd_sum, self.f = np.zeros_like(P), f
            self.psd_sum += P * (s1 - s0)
            self.psd_w += s1 - s0
            self.spec_t.append(float(tc[s0]))
            self.spec_cols.append(P[:, 3])

        # Peak candidates on the resultant, with a full-rate window around each
        dist = max(int(PEAK_SPACING_S * self.fs), 1)
        idx, _ = signal.find_peaks(res, distance=dist)
        if not len(idx):
            idx = np.array([int(np.argmax(res))])
        half = int(PEAK_HALF_S * self.fs)
        for i in idx[np.argsort(res[idx])[::-1][:N_EVENTS]]:
            j = c0 + int(i)
            a, b = max(j - half, 0), min(j + half + 1, len(t))
            self.cands.append({"t": float(t[j]), "r": float(res_all[j]), "xyz": X[j].astype(float).tolist(),
                               "snip_t": t[a:b].astype(np.float64), "snip": X[a:b].astype(np.float32)})
        self._prune(2 * N_EVENTS)

        # Band-limited vibration RMS at 10 Hz (motors, engines, propellers)
        if self.sos is not None and len(X) > 30:
            v = np.linalg.norm(signal.sosfiltfilt(self.sos, X - X.mean(axis=0), axis=0), axis=1)[c0:c1]
            w = self.vib_w
            n = len(v) // w
            if n:
                self.vib_v.append(np.sqrt((v[: n * w] ** 2).reshape(n, w).mean(axis=1)))
                self.vib_t.append(tc[: n * w: w] + 0.05)

    def _prune(self, keep: int) -> None:
        picked: list[dict] = []
        for c in sorted(self.cands, key=lambda c: -c["r"]):
            if all(abs(c["t"] - p["t"]) >= PEAK_SPACING_S for p in picked):
                picked.append(c)
            if len(picked) >= keep:
                break
        self.cands = picked

    def write(self, out: Path, ch_id: int) -> None:
        self._prune(N_EVENTS)
        top = max((c["r"] for c in self.cands), default=0.0)
        events = [c for c in self.cands if c["r"] >= 0.3 * top] or self.cands[:1]
        mean = self.r_sum / max(self.r_n, 1)
        doc: dict = {
            "fs": self.fs, "samples": self.r_n,
            "resultant": {"mean_g": mean, "rms_g": math.sqrt(max(self.r_sq / max(self.r_n, 1) - mean ** 2, 0.0))},
            "events": [{"t": c["t"], "resultant_g": c["r"], "x_g": c["xyz"][0], "y_g": c["xyz"][1], "z_g": c["xyz"][2]}
                       for c in events],
            "vibration_band_hz": list(self.vib_band),
        }
        if self.psd_sum is not None:
            P = self.psd_sum / max(self.psd_w, 1)
            doc["psd"] = {"f": self.f.tolist(), **{k: P[:, i].tolist() for i, k in enumerate(("x", "y", "z", "resultant"))}}
            doc["spectrogram"] = self._spectrogram()
        if self.vib_v:
            doc["vibration"] = {"t": np.concatenate(self.vib_t).round(3).tolist(),
                                "rms_g": np.concatenate(self.vib_v).astype(np.float32).tolist()}
        (out / f"full_{ch_id}.json").write_text(json.dumps(doc))
        np.savez_compressed(out / f"full_{ch_id}.npz",
                            **{f"t{i}": c["snip_t"] for i, c in enumerate(events)},
                            **{f"x{i}": c["snip"] for i, c in enumerate(events)})

    def _spectrogram(self) -> dict:
        f = self.f
        cols = np.array(self.spec_cols).T          # [f, t]
        ts = np.array(self.spec_t)
        if cols.shape[1] > SPEC_COLS:              # merge neighbouring columns
            g = math.ceil(cols.shape[1] / SPEC_COLS)
            n = cols.shape[1] // g * g
            cols = np.concatenate([cols[:, :n].reshape(len(f), -1, g).mean(axis=2), cols[:, n:]], axis=1) \
                if n < cols.shape[1] else cols.reshape(len(f), -1, g).mean(axis=2)
            ts = ts[::g][: cols.shape[1]]
        sel = (f > 0) & (f <= min(self.fs / 2, 1000.0))
        f, cols = f[sel], cols[sel]
        edges = np.logspace(np.log10(max(f[0], 1.0)), np.log10(f[-1]), SPEC_ROWS + 1)
        rows = []
        for a, b in zip(edges[:-1], edges[1:]):
            m = (f >= a) & (f < b)
            rows.append(cols[m].mean(axis=0) if m.any() else np.full(cols.shape[1], np.nan))
        Z = np.log10(np.maximum(np.array(rows), 1e-12))
        Z = np.where(np.isfinite(Z), Z, np.nanmin(Z))
        return {"t": [round(float(v), 2) for v in ts], "f": [round(float(v), 2) for v in np.sqrt(edges[:-1] * edges[1:])],
                "log10_psd": np.round(Z, 3).tolist(), "column": "resultant",
                "method": "Welch PSD of the resultant per time section, full sample rate, log-binned for display"}


def stream_channel(ea, cols: list[tuple[int, str]], k: int, t0_us: float, out: Path, ch_id: int,
                   fs: float, cfg, stats: bool, progress=None) -> tuple[pd.DataFrame, int]:
    """Read ea (an idelib EventArray) in slices. Writes env_/full_ files and returns the averaged table."""
    lc = cfg.large_recordings
    n = len(ea)
    e = max(int(lc.envelope_factor), 1) * k
    fr = None
    unit = e
    if stats:
        bw = 1.0 if fs >= 400 else max(fs / 400, 0.1)
        nper = max(int(fs / bw), 16)
        seg = max(nper, math.ceil(n / SPEC_COLS))
        fr = FullRate(fs, n, seg, nper)
        seg = math.ceil(seg / math.lcm(e, fr.vib_w)) * math.lcm(e, fr.vib_w)
        fr.seg = seg
        unit = seg
    size = max(unit, (int(lc.slice_rows) // unit) * unit)
    pad = int(PEAK_HALF_S * fs) + 1 if stats else 0

    avg_t, avg_v, env_t, env_lo, env_hi = [], [], [], [], []
    for s0 in range(0, n, size):
        s1 = min(s0 + size, n)
        a0, a1 = max(s0 - pad, 0), min(s1 + pad, n)
        arr = ea.arraySlice(a0, a1)
        t = (np.asarray(arr[0], dtype=np.float64) - t0_us) / 1e6
        V = np.asarray(arr[1:], dtype=np.float64).T          # [n, sub]
        c0, c1 = s0 - a0, s0 - a0 + (s1 - s0)
        if fr is not None:
            fr.add(t, V[:, :3], c0, c1)
        tc, Vc = t[c0:c1], V[c0:c1]
        m = len(tc) // k * k                # a final part block (< k samples) is dropped
        if m:
            avg_t.append(tc[:m].reshape(-1, k).mean(axis=1))
            avg_v.append(Vc[:m].reshape(-1, k, V.shape[1]).mean(axis=1).astype(np.float32))
        me = len(tc) // e * e
        if me:
            env_t.append(tc[:me].reshape(-1, e).mean(axis=1))
            env_lo.append(Vc[:me].reshape(-1, e, V.shape[1]).min(axis=1).astype(np.float32))
            env_hi.append(Vc[:me].reshape(-1, e, V.shape[1]).max(axis=1).astype(np.float32))
        if progress:
            progress(s1 / n)
        del arr, t, V

    T = np.concatenate(avg_t)
    A = np.concatenate(avg_v)
    df = pd.DataFrame({"t": T})
    for i, name in cols:
        if i < A.shape[1]:
            df[name] = A[:, i]
    if env_t and k > 1:
        lo, hi = np.concatenate(env_lo), np.concatenate(env_hi)
        edf = pd.DataFrame({"t": np.concatenate(env_t)})
        for i, name in cols:
            if i < lo.shape[1]:
                edf[f"{name}__min"] = lo[:, i]
                edf[f"{name}__max"] = hi[:, i]
        edf.to_parquet(out / f"env_{ch_id}.parquet", index=False)
    if fr is not None:
        fr.write(out, ch_id)
    return df, n
