"""Recording uploads sent in pieces, so any size of file gets through the 30 s
request limit and the proxy's body limit. The browser sends the pieces in order;
the file is put back together on local disk and read in the background."""
from __future__ import annotations

import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlmodel import select

from ..config import get_config
from . import bus
from . import services as S
from .db import Recording, session

log = logging.getLogger("engine")
# Long files are read one at a time, apart from hunt processing (services.POOL)
BIG = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bigfile")
MAX_BYTES = 4 << 30
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def chunk_bytes() -> int:
    return int(get_config().large_recordings.chunk_mb) << 20


def _path(job_id: str) -> Path:
    return S.dirs()["uploads"] / f".chunked-{job_id}"


def _public(j: dict) -> dict:
    return {k: v for k, v in j.items() if not k.startswith("_")}


def start(filename: str, size: int, title: str, description: str, profile: str, in_library: bool) -> dict:
    _cleanup()
    if size <= 0:
        raise ValueError("empty file")
    if size > MAX_BYTES:
        raise ValueError(f"file is larger than {MAX_BYTES >> 30} GB")
    free = shutil.disk_usage(S.dirs()["uploads"]).free
    if size * 2 > free:                              # the file plus its parsed bundle
        raise ValueError(f"not enough disk space on the server for a {size >> 20} MB file")
    job_id = uuid.uuid4().hex
    _path(job_id).write_bytes(b"")
    j = {"id": job_id, "filename": filename, "size": size, "received": 0, "status": "receiving",
         "progress": 0.0, "recording_id": None, "error": None, "chunk_bytes": chunk_bytes(),
         "_meta": {"title": title, "description": description, "profile": profile, "in_library": in_library},
         "_touched": time.time()}
    with _lock:
        _jobs[job_id] = j
    return _public(j)


def get(job_id: str) -> dict:
    j = _jobs.get(job_id)
    if not j:
        raise KeyError(job_id)
    return _public(j)


def put(job_id: str, offset: int, data: bytes) -> dict:
    j = _jobs.get(job_id)
    if not j:
        raise KeyError(job_id)
    if j["status"] != "receiving":
        raise ValueError("upload already finished")
    if offset > j["received"] or offset < 0:
        raise ValueError(f"expected the piece at byte {j['received']}")
    if offset + len(data) > j["size"]:
        raise ValueError("piece runs past the end of the file")
    with open(_path(job_id), "r+b") as f:            # a resent piece overwrites itself
        f.seek(offset)
        f.write(data)
    j["received"] = max(j["received"], offset + len(data))
    j["_touched"] = time.time()
    return _public(j)


def finish(job_id: str) -> dict:
    j = _jobs.get(job_id)
    if not j:
        raise KeyError(job_id)
    if j["status"] != "receiving":
        return _public(j)
    if j["received"] != j["size"] or _path(job_id).stat().st_size != j["size"]:
        raise ValueError(f"only {j['received']} of {j['size']} bytes arrived")
    j["status"] = "processing"
    BIG.submit(_process, job_id)
    return _public(j)


def cancel(job_id: str) -> None:
    j = _jobs.pop(job_id, None)
    if j and j["status"] == "receiving":
        _path(job_id).unlink(missing_ok=True)


def _process(job_id: str) -> None:
    j = _jobs[job_id]
    last = [0.0]

    def progress(f: float) -> None:
        j["progress"] = round(min(max(f, 0.0), 1.0), 3)
        j["_touched"] = time.time()
        if time.time() - last[0] > 1.0:
            last[0] = time.time()
            bus.publish("upload_job", _public(j))

    try:
        up = S.ingest_file(_path(job_id), j["filename"], progress=progress)
        if up.status != "parsed":
            log.warning("large upload %s not readable: %s", j["filename"], up.error)
            raise ValueError("This file could not be read as an enDAQ recording. Check it is the .IDE file "
                             "from the sensor and that it opens in enDAQ Lab.")
        with session() as s:
            rec = s.exec(select(Recording).where(Recording.upload_id == up.id)).first()
        if rec is None:
            m = j["_meta"]
            rec = S.create_recording(up, m["title"] or Path(up.filename).stem, m["description"] or None,
                                     m["profile"], m["in_library"])
        j.update(status="done", progress=1.0, recording_id=rec.id)
    except Exception as ex:
        log.exception("large upload failed")
        j.update(status="error", error=f"{type(ex).__name__}: {ex}" if not isinstance(ex, ValueError) else str(ex))
    finally:
        _path(job_id).unlink(missing_ok=True)
        S.release_memory()
        j["_touched"] = time.time()
        bus.publish("upload_job", _public(j))
        bus.publish("recording", {"recording_id": j.get("recording_id")})


def _cleanup(max_age_s: float = 6 * 3600) -> None:
    """Forget uploads abandoned part way (closed tab, lost Wi-Fi) and finished jobs."""
    cut = time.time() - max_age_s
    with _lock:
        for jid, j in list(_jobs.items()):
            if j["_touched"] < cut and j["status"] != "processing":
                _jobs.pop(jid)
                _path(jid).unlink(missing_ok=True)
        for f in S.dirs()["uploads"].glob(".chunked-*"):     # left over from a restart
            if f.name[len(".chunked-"):] not in _jobs and f.stat().st_mtime < time.time() - 3600:
                f.unlink(missing_ok=True)
