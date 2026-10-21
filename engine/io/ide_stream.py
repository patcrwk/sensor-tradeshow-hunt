"""Open a large .IDE without holding its samples in memory.

idelib's importFile keeps every data block's payload in memory and then copies
each channel into one array (about twice the file size), and its arraySlice
rebuilds the whole channel's time base on every call. For a 300 MB flight that
is far more than a small server has. Here:

    1. the file is parsed with idelib's own parsers (channels, calibration,
       block timing), but each block's payload is dropped as soon as it is
       parsed; only block metadata stays in memory
    2. low-rate channels (pressure, temperature, light, GPS) are reloaded and
       cached in full, so idelib's normal API works on them and calibrations
       that reference them stay correct
    3. high-rate channels are read through BlockReader, which decodes only the
       blocks a requested range touches, straight from the file
"""
from __future__ import annotations

import logging

import numpy as np
from numpy.lib import recfunctions as rfn

log = logging.getLogger(__name__)
_SWEEP_EVERY = 256


def open_streaming(path, keep_rows: int, progress=None):
    """Parse path; channels with at most keep_rows samples are loaded in full.
    Returns (doc, counts) where counts maps channel id to sample count."""
    import idelib.importer as imp
    from idelib import parsers

    stream = open(path, "rb")
    doc = imp.openFile(stream, quiet=True)
    elementParsers = doc._parsers
    size = max(stream.seek(0, 2), 1)
    seen: dict[int, int] = {}

    def sweep():
        for ch in doc.channels.values():
            for ea in ch.sessions.values():
                data = ea._data
                for b in data[seen.get(id(ea), 0):]:
                    _drop(b)
                seen[id(ea)] = len(data)

    for n, el in enumerate(doc.ebmldoc):
        if el is None or el.name not in elementParsers:
            continue
        p = elementParsers[el.name]
        if p.isHeader and el.name != "Attribute":
            continue
        try:
            p.parse(el, timeOffset=0)
        except parsers.ParsingError as err:
            log.error("Parsing error during import: %s", err)
            continue
        if n % _SWEEP_EVERY == 0:
            sweep()
            if progress:
                progress(el.offset / size)
    sweep()

    counts = {}
    for cid, ch in doc.channels.items():
        ea = ch.getSession()
        counts[int(cid)] = len(ea)
        if len(ea) <= keep_rows:                     # small: load fully, use idelib as usual
            for b in ea._data:
                b._payload = _payload(ea, b)
                # block summaries: temperature-compensated calibrations read them
                vals = rfn.structured_to_unstructured(b._payload)
                b.min, b.mean, b.max = vals.min(axis=0), vals.mean(axis=0), vals.max(axis=0)
            ea.fillCache()
    doc.loading = False
    return doc, counts


def _drop(b) -> None:
    """Free a parsed block's samples and summaries; its timing and file position stay."""
    b._payload = None
    if b._payloadEl is not None:
        b._payloadEl.gc()
    b.min = b.mean = b.max = None        # per-block summaries, not used here
    b._minMeanMaxEl = b._minMeanMax = None
    b.element = None


def _payload(ea, b) -> np.ndarray:
    if b._payload is not None:
        return b._payload
    raw = np.frombuffer(b._payloadEl.value, dtype=ea._npType)
    b._payloadEl.gc()
    return raw


def first_time(ea) -> float | None:
    return float(ea._data[0].startTime) if ea._data else None


def rate_hz(ea) -> float:
    n = len(ea)
    if n < 2 or not ea._data:
        return 0.0
    return (n - 1) / max((ea._data[-1].endTime - ea._data[0].startTime) / 1e6, 1e-9)


class BlockReader:
    """arraySlice for one channel that decodes only the blocks it needs.
    Same output as idelib's EventArray.arraySlice: rows are time (us) then
    one row per subchannel, calibrated."""

    def __init__(self, ea):
        self.ea = ea
        self.blocks = ea._data
        self.starts = np.array([b.indexRange[0] for b in self.blocks], dtype=np.int64)
        self.n = len(ea)
        self.xform = ea._fullXform if ea.useAllTransforms else ea._comboXform

    def __len__(self) -> int:
        return self.n

    def arraySlice(self, start: int, end: int) -> np.ndarray:
        start, end = max(int(start), 0), min(int(end), self.n)
        if end <= start:
            return np.empty((len(self.ea._npType.names or [0]) + 1, 0))
        i0 = int(np.searchsorted(self.starts, start, side="right")) - 1
        i1 = int(np.searchsorted(self.starts, end, side="left"))
        raws, times = [], []
        for b in self.blocks[i0:i1]:
            raws.append(_payload(self.ea, b))
            m = b.numSamples
            if m > 1:
                times.append(b.startTime + np.arange(m) * ((b.endTime - b.startTime) / (m - 1)))
            else:
                times.append(np.array([float(b.startTime)]))
        off = self.blocks[i0].indexRange[0]
        raw = np.concatenate(raws)[start - off:end - off]
        t = np.concatenate(times)[start - off:end - off]
        vals = rfn.structured_to_unstructured(raw).T
        out = np.empty((vals.shape[0] + 1, vals.shape[1]))
        out[0] = t
        self.xform.inplace(vals, out=out[1:], timestamp=out[0], noBivariates=self.ea.noBivariates)
        if getattr(self.ea, "removeMean", False):
            out[1:] -= out[1:].mean(axis=1, keepdims=True)
        return out
