"""Watch folder: poll for new .IDE files (for example a sensor mounted as a USB drive).

Polling is used instead of filesystem events because USB volumes come and go
and events are unreliable on removable media. The folder may be a glob such
as /Volumes/*/DATA.
"""
from __future__ import annotations

import glob
import logging
import threading
import time
from pathlib import Path

from . import bus
from .db import get_setting

log = logging.getLogger("engine.watcher")
_seen: dict[str, tuple[float, int]] = {}
_stop = threading.Event()
state = {"folder": None, "last_scan": None, "found": 0, "error": None}


def scan_once() -> list[str]:
    from .services import ingest_file
    folder = get_setting("watch_folder", "") or ""
    state["folder"] = folder
    state["last_scan"] = time.time()
    if not folder:
        return []
    new = []
    for d in glob.glob(folder):
        for p in Path(d).glob("*"):
            if p.suffix.upper() != ".IDE" and not p.name.lower().endswith(".synth.zip"):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            key = str(p)
            sig = (st.st_mtime, st.st_size)
            prev = _seen.get(key)
            _seen[key] = sig
            # Only ingest once the file is stable across two scans (copy finished)
            if prev is None or prev != sig or key.endswith("#done"):
                continue
            if _seen.get(key + "#done") == sig:
                continue
            _seen[key + "#done"] = sig
            try:
                up = ingest_file(p, p.name, source_path=key)
                new.append(up.filename)
                state["found"] += 1
                bus.publish("upload", {"upload_id": up.id, "filename": up.filename, "source": "watch"})
            except Exception as ex:  # never stop the watcher
                state["error"] = str(ex)
                log.exception("watch ingest failed")
    return new


def _loop(interval: float):
    while not _stop.is_set():
        try:
            scan_once()
        except Exception as ex:
            state["error"] = str(ex)
        _stop.wait(interval)


def start(interval: float = 3.0) -> None:
    t = threading.Thread(target=_loop, args=(interval,), daemon=True, name="watcher")
    t.start()


def stop() -> None:
    _stop.set()
