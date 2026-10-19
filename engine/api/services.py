"""Orchestration: uploads, run processing, courses, explorer recordings."""
from __future__ import annotations

import io
import json
import logging
import shutil
import threading
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from sqlmodel import select

from ..config import data_dir, get_config
from ..course import image_fit
from ..course.survey import SurveyError, derive_course, finalize, runtime_course, spacing_warnings
from ..explorer.analyze import analyze, restory
from ..hunt.matching import candidate_runs
from ..hunt.scoring import summarize
from ..hunt.validation import process_run
from ..io.bundle import Bundle, open_bundle
from ..io.ide_reader import ide_to_bundle, sha256_file
from ..synthetic.generator import unzip_bundle
from . import bus, storage
from .db import (AuditLog, Course, Participant, Recording, Run, Scan, Sensor, SurveyFile, Upload, audit,
                 current_event, get_setting, now, session, set_setting)

log = logging.getLogger("engine")
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="proc")
_ingest_lock = threading.Lock()


def dirs() -> dict[str, Path]:
    d = data_dir()
    out = {k: d / k for k in ("uploads", "bundles")}     # local caches; durable data goes through storage
    for p in out.values():
        p.mkdir(parents=True, exist_ok=True)
    return out


# -- uploads --------------------------------------------------------------------

def ingest_bytes(filename: str, data: bytes, source_path: str | None = None) -> Upload:
    tmp = dirs()["uploads"] / f".incoming-{threading.get_ident()}"
    tmp.write_bytes(data)
    try:
        return ingest_file(tmp, filename, source_path)
    finally:
        tmp.unlink(missing_ok=True)


def ingest_file(path: Path, filename: str | None = None, source_path: str | None = None,
                progress=None) -> Upload:
    """Hash, store and parse a recording. Re-uploading the same file returns the existing row.

    Normal files keep the original in storage and rebuild the local bundle from it.
    Long recordings (read in slices) keep the finished bundle instead of the
    original, so a multi-hour flight does not fill the database."""
    filename = filename or path.name
    sha = sha256_file(path)
    with _sha_lock(sha):
        with session() as s:
            existing = s.exec(select(Upload).where(Upload.sha256 == sha)).first()
            if existing and existing.status == "parsed":
                return existing
        ext = _ext(filename)
        key = f"upload/{sha[:16]}{ext}"
        up = existing or Upload(sha256=sha, filename=filename, size=path.stat().st_size, path=key,
                                source_path=source_path)
        try:
            if ext == ".synth.zip":
                storage.put(key, path.read_bytes())
                b = _build_bundle(key, sha)
            else:
                bdir = dirs()["bundles"] / sha[:16]
                b = ide_to_bundle(path, bdir, file_hash=sha, progress=progress)
                if b.reduced:
                    key = f"upload/{sha[:16]}.bundle.zip"
                    storage.put(key, zip_bundle(bdir))
                elif not storage.exists(key):
                    storage.put(key, path.read_bytes())   # the original is what survives restarts
            m = b.meta
            up.path = key
            up.bundle_dir = sha[:16]
            up.status = "parsed"
            up.error = None
            up.serial = str(m["device"].get("serial")) if m["device"].get("serial") is not None else None
            up.model = m["device"].get("model")
            up.start_epoch = m.get("start_epoch")
            up.duration_s = m.get("duration_s")
            up.has_gps = b.has_gps
            up.synthetic = bool(m.get("synthetic"))
        except Exception as ex:
            log.exception("parse failed")
            up.status = "error"
            up.error = f"{type(ex).__name__}: {ex}"
        with session() as s:
            s.add(up)
            s.commit()
            s.refresh(up)
            if up.serial:
                sen = s.get(Sensor, up.serial) or Sensor(serial=up.serial)
                sen.model = up.model
                sen.has_gps = up.has_gps
                sen.last_seen = now()
                s.add(sen)
                s.commit()
    return up


_sha_locks: dict[str, threading.Lock] = {}


def _sha_lock(sha: str) -> threading.Lock:
    """One parse per file at a time, without making other uploads wait for a long one."""
    with _ingest_lock:
        return _sha_locks.setdefault(sha, threading.Lock())


def zip_bundle(bdir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:     # parquet and npz are already compressed
        for f in sorted(bdir.iterdir()):
            if f.is_file():
                z.write(f, f.name)
    return buf.getvalue()


def _ext(filename: str) -> str:
    return ".synth.zip" if filename.lower().endswith(".zip") else Path(filename).suffix.lower() or ".ide"


def _build_bundle(key: str, sha: str) -> Bundle:
    """Parse the stored original into the local bundle cache."""
    bdir = dirs()["bundles"] / sha[:16]
    if key.endswith(".synth.zip") or key.endswith(".bundle.zip"):
        unzip_bundle(storage.get(key), bdir)
        return open_bundle(bdir)
    local = storage.to_local(key, dirs()["uploads"] / Path(key).name) if not key.startswith("/") else Path(key)
    return ide_to_bundle(local, bdir, file_hash=sha)


def bundle_for(upload_id: int) -> Bundle:
    with session() as s:
        up = s.get(Upload, upload_id)
    if not up or up.status != "parsed":
        raise ValueError("upload not parsed")
    return _bundle(up.sha256, up.path)


_bundle_lock = threading.Lock()


@lru_cache(maxsize=6)
def _bundle(sha: str, key: str) -> Bundle:
    bdir = dirs()["bundles"] / sha[:16]
    if not (bdir / "meta.json").exists():
        with _bundle_lock:                          # cache wiped (Heroku restart): rebuild once
            if not (bdir / "meta.json").exists():
                log.info("rebuilding cached bundle %s from stored original", sha[:16])
                _build_bundle(key, sha)
    return open_bundle(bdir)


def upload_candidates(up: Upload) -> list[dict]:
    ev = current_event()
    with session() as s:
        rows = s.exec(select(Run, Participant).where(Run.event_id == ev.id, Run.status == "out",
                                                     Run.participant_id == Participant.id)).all()
    open_runs = [{"id": r.id, "serial": r.sensor_serial, "checkout_epoch": r.checkout_epoch,
                  "name": p.display_name} for r, p in rows]
    return candidate_runs(up.serial, up.start_epoch, open_runs)


# -- runs -----------------------------------------------------------------------

def active_course() -> Course | None:
    cid = get_setting("active_course_id")
    if not cid:
        return None
    with session() as s:
        return s.get(Course, cid)


def attach_upload(run_id: int, upload_id: int) -> Run:
    with session() as s:
        run = s.get(Run, run_id)
        up = s.get(Upload, upload_id)
        if run is None or up is None:
            raise KeyError("run or upload not found")
        run.upload_id = upload_id
        run.status = "processing"
        s.add(run)
        s.commit()
        s.refresh(run)
    audit("attach", f"upload {up.filename}", run_id=run_id)
    bus.publish("run", {"run_id": run_id, "status": "processing"})
    POOL.submit(_process_safe, run_id)
    return run


def _process_safe(run_id: int, course_id: int | None = None) -> None:
    try:
        process(run_id, course_id)
    except Exception as ex:
        log.exception("processing failed")
        with session() as s:
            run = s.get(Run, run_id)
            run.status = "needs_review"
            run.error = f"{type(ex).__name__}: {ex}"
            s.add(run)
            s.commit()
        audit("error", traceback.format_exc()[-1500:], run_id=run_id)
        bus.publish("run", {"run_id": run_id, "status": "needs_review"})


def process(run_id: int, course_id: int | None = None) -> Run:
    with session() as s:
        run = s.get(Run, run_id)
    course_row = None
    if course_id:
        with session() as s:
            course_row = s.get(Course, course_id)
    elif run.course_id and run.status in ("published", "needs_review") and run.result_path:
        with session() as s:
            course_row = s.get(Course, run.course_id)
    else:
        course_row = active_course()
    course_doc = runtime_course(course_row.data) if course_row and course_row.data else None
    b = bundle_for(run.upload_id)
    res = process_run(b, course_doc, get_config(), overrides=run.overrides, scans=run_scans(run_id, course_doc))
    res["course"] = {"id": course_row.id, "name": course_row.name, "version": course_row.version} if course_row else None
    key = storage.put_json(f"result/run_{run_id}.json", res)
    summ = summarize(res, course_doc)
    auto = get_setting("auto_publish", True)
    with session() as s:
        run = s.get(Run, run_id)
        run.result_path = key
        run.summary = summ
        run.elapsed_s = res["elapsed_s"]
        run.complete = bool(res["complete"])
        run.positioning_mode = res["positioning_mode"]
        run.course_id = course_row.id if course_row else None
        run.course_version = course_row.version if course_row else None
        run.processed_at = now()
        run.error = None
        was_published = run.status == "published"
        if res["needs_review"] and not was_published:
            run.status = "needs_review"
        elif auto or was_published:
            run.status = "published"
            run.published_at = run.published_at or now()
        else:
            run.status = "needs_review"
        s.add(run)
        s.commit()
        s.refresh(run)
    bus.publish("run", {"run_id": run_id, "status": run.status})
    if run.status == "published":
        bus.publish("leaderboard", {})
    try:
        ensure_run_recording(run_id)
    except Exception:
        log.exception("could not add the run to Recording Explorer")
    return run


def run_scans(run_id: int, course_doc: dict | None = None) -> list[dict]:
    """QR scans for a run, with station names, oldest first."""
    with session() as s:
        rows = s.exec(select(Scan).where(Scan.run_id == run_id).order_by(Scan.at)).all()
    if course_doc is None:
        c = active_course()
        course_doc = c.data if c and c.data else {}
    names = {st["id"]: st["name"] for st in course_doc.get("stations", [])}
    names["BOOTH"] = "Start and finish"
    return [{"station": r.station, "station_name": names.get(r.station, r.station), "at": r.at} for r in rows]


def load_result(run: Run) -> dict | None:
    return storage.get_json(run.result_path)


def set_overrides(run_id: int, checkins: list[dict] | None, note: str) -> Run:
    with session() as s:
        run = s.get(Run, run_id)
        run.overrides = {"checkins": checkins} if checkins is not None else None
        s.add(run)
        s.commit()
    audit("override" if checkins is not None else "override_cleared", note, run_id=run_id,
          data={"checkins": checkins})
    return process(run_id)


def publish_run(run_id: int, publish: bool = True, note: str | None = None) -> Run:
    with session() as s:
        run = s.get(Run, run_id)
        run.status = "published" if publish else "needs_review"
        run.published_at = now() if publish else None
        s.add(run)
        s.commit()
        s.refresh(run)
    audit("publish" if publish else "unpublish", note, run_id=run_id)
    bus.publish("run", {"run_id": run_id, "status": run.status})
    bus.publish("leaderboard", {})
    return run


def rescore_all(course_id: int) -> int:
    ev = current_event()
    with session() as s:
        runs = s.exec(select(Run).where(Run.event_id == ev.id, Run.upload_id != None)).all()  # noqa: E711
    for r in runs:
        POOL.submit(_process_safe, r.id, course_id)
    audit("rescore", f"{len(runs)} runs against course {course_id}", course_id=course_id)
    return len(runs)


# -- courses --------------------------------------------------------------------

def create_course(name: str, upload_ids: list[int], mode: str | None = None, lineage: int | None = None) -> Course:
    ev = current_event()
    with session() as s:
        c = Course(event_id=ev.id, name=name, status="processing", lineage=lineage)
        if lineage:
            prev = s.exec(select(Course).where(Course.lineage == lineage)).all()
            c.version = max([p.version for p in prev] + [1]) + 1
        s.add(c)
        s.commit()
        s.refresh(c)
        if not lineage:
            c.lineage = c.id
            s.add(c)
            s.commit()
        for uid in upload_ids:
            s.add(SurveyFile(course_id=c.id, upload_id=uid))
        s.commit()
    derive(c.id, mode)
    with session() as s:
        return s.get(Course, c.id)


def survey_bundles(course_id: int) -> list[Bundle]:
    with session() as s:
        files = s.exec(select(SurveyFile).where(SurveyFile.course_id == course_id)).all()
    return [bundle_for(f.upload_id) for f in files]


def derive(course_id: int, mode: str | None = None) -> Course:
    try:
        doc = derive_course(survey_bundles(course_id), get_config(), mode)
        status, err = "draft", None
    except (SurveyError, ValueError) as ex:
        doc, status, err = None, "needs_review", str(ex)
    except Exception as ex:
        log.exception("course derivation failed")
        doc, status, err = None, "needs_review", f"{type(ex).__name__}: {ex}"
    with session() as s:
        c = s.get(Course, course_id)
        if doc is not None and c.data:
            if c.data.get("background"):
                doc["background"] = c.data["background"]
            if c.data.get("qr_codes"):                 # printed signs must keep working
                doc["qr_codes"] = {**doc.get("qr_codes", {}), **c.data["qr_codes"]}
        if doc is not None:
            apply_plan(doc)
            apply_station_term(doc)
        c.data = doc
        c.status = status
        c.error = err
        s.add(c)
        s.commit()
        s.refresh(c)
    bus.publish("course", {"course_id": course_id})
    return c


EDITABLE_STATION = {"name", "x", "y", "required", "tap_count", "beacon_hz", "orientation"}


def edit_course(course_id: int, patch: dict) -> Course:
    cfg = get_config()
    with session() as s:
        c = s.get(Course, course_id)
        doc = json.loads(json.dumps(c.data))
    if "name" in patch:
        with session() as s:
            c = s.get(Course, course_id)
            c.name = patch["name"]
            s.add(c)
            s.commit()
    moved = False
    for sp in patch.get("stations", []):
        st = next((x for x in doc["stations"] if x["id"] == sp["id"]), None)
        if not st:
            continue
        for k, v in sp.items():
            if k in EDITABLE_STATION:
                if k in ("x", "y") and v != st.get(k):
                    moved = True
                    st.setdefault("edited", []).append(k)
                    st["source"] = {**st.get("source", {}), "method": "moved by staff on the review screen"}
                st[k] = v
    for k in ("order_rule", "match_radius_m", "identity_methods", "positioning_mode"):
        if k in patch:
            doc[k] = patch[k]
    if patch.get("rotate_deg") or patch.get("mirror"):
        _orient_course(doc, float(patch.get("rotate_deg") or 0), bool(patch.get("mirror")))
        moved = True
    if "par_time_s" in patch:
        doc["par"]["par_time_s"] = patch["par_time_s"]
        doc["par"]["edited"] = True
    if moved:
        from ..position.projection import LocalFrame
        fr = LocalFrame.from_dict(doc.get("frame"))
        for st in doc["stations"]:
            if fr:
                lat, lon = fr.to_latlon(st["x"], st["y"])
                st["lat"], st["lon"] = float(lat), float(lon)
        doc = finalize({**doc, "identity_methods": doc["identity_methods"]}, cfg)
    doc["warnings"] = spacing_warnings(doc, cfg)
    if doc.get("background", {}).get("pins"):
        _refit(doc)
    with session() as s:
        c = s.get(Course, course_id)
        c.data = doc
        s.add(c)
        s.commit()
        s.refresh(c)
    audit("course_edit", json.dumps(patch)[:500], course_id=course_id)
    bus.publish("course", {"course_id": course_id})
    return c


def ensure_codes(course_id: int) -> Course:
    """Give a course its station QR codes if it has none yet (older courses)."""
    from ..course.survey import ensure_qr_codes
    with session() as s:
        c = s.get(Course, course_id)
        if c.data and not c.data.get("qr_codes"):
            doc = json.loads(json.dumps(c.data))
            ensure_qr_codes(doc)
            apply_plan(doc)
            c.data = doc
            s.add(c)
            s.commit()
            s.refresh(c)
    return c


# -- QR station plan: print signs before the course is mapped -------------------

def qr_plan() -> dict:
    """{count, codes: {BOOTH, S1..}, names: {S1: ...}}. Codes are never changed or removed once made,
    so signs that were printed keep working when the count changes."""
    return get_setting("qr_plan") or {"count": 0, "codes": {}, "names": {}}


def set_qr_plan(count: int, names: dict | None = None) -> dict:
    import secrets
    plan = qr_plan()
    count = max(0, min(int(count), 99))
    codes = dict(plan.get("codes") or {})
    for sid in ["BOOTH"] + [f"S{i}" for i in range(1, count + 1)]:
        codes.setdefault(sid, secrets.token_urlsafe(6))
    plan = {"count": count, "codes": codes,
            "names": {**(plan.get("names") or {}), **{k: v for k, v in (names or {}).items() if v}}}
    set_setting("qr_plan", plan)
    # Courses that already exist adopt the planned codes for matching station numbers
    with session() as s:
        for c in s.exec(select(Course)).all():
            if c.data:
                doc = json.loads(json.dumps(c.data))
                if apply_plan(doc, plan):
                    c.data = doc
                    s.add(c)
        s.commit()
    audit("qr_plan", f"{count} stations")
    bus.publish("course", {})
    return plan


def apply_plan(doc: dict, plan: dict | None = None) -> bool:
    """Make a course use the planned code for every station it shares with the plan."""
    plan = plan or qr_plan()
    pcodes = plan.get("codes") or {}
    if not pcodes:
        return False
    codes = doc.setdefault("qr_codes", {})
    ids = ["BOOTH"] + [st["id"] for st in doc.get("stations", [])]
    changed = False
    for sid in ids:
        if sid in pcodes and codes.get(sid) != pcodes[sid]:
            codes[sid] = pcodes[sid]
            changed = True
    names = plan.get("names") or {}
    for st in doc.get("stations", []):           # planned names replace default ones
        nm = names.get(st["id"])
        if nm and st.get("name") == f"Station {st.get('number')}":
            st["name"] = nm
            changed = True
    return changed


def apply_station_term(doc: dict) -> None:
    """Default names follow the sign wording: "Waypoint 3" rather than "Station 3"."""
    term = (get_setting("branding") or {}).get("station_term") or "Waypoint"
    for st in doc.get("stations", []):
        if st.get("name") == f"Station {st.get('number')}":
            st["name"] = f"{term} {st['number']}"


def _orient_course(doc: dict, rotate_deg: float, mirror: bool) -> None:
    """Turn or flip the whole course map about the booth. Without GPS the compass direction of
    a mapped course is unknown, so staff line it up with the hall by eye."""
    import math
    bx, by = doc["booth"]["x"], doc["booth"]["y"]
    a = math.radians(rotate_deg)
    c, s_ = math.cos(a), math.sin(a)

    def tf(x, y):
        x, y = x - bx, y - by
        if mirror:
            x = -x
        return round(c * x - s_ * y + bx, 2), round(s_ * x + c * y + by, 2)

    for st in doc["stations"]:
        st["x"], st["y"] = tf(st["x"], st["y"])
    r = doc.get("route") or {}
    if r.get("x"):
        pts = [tf(x, y) for x, y in zip(r["x"], r["y"])]
        r["x"], r["y"] = [p[0] for p in pts], [p[1] for p in pts]
    o = doc.setdefault("orientation_edit", {"rotate_deg": 0, "mirror": False})
    o["rotate_deg"] = (o["rotate_deg"] + rotate_deg) % 360
    o["mirror"] = o["mirror"] != mirror


def publish_course(course_id: int) -> Course:
    with session() as s:
        c = s.get(Course, course_id)
        if not c.data:
            raise ValueError("course has no derived data")
        for other in s.exec(select(Course).where(Course.lineage == c.lineage, Course.status == "published")).all():
            if other.id != c.id:
                other.status = "archived"
                s.add(other)
        c.status = "published"
        c.published_at = now()
        s.add(c)
        s.commit()
        s.refresh(c)
    set_setting("active_course_id", course_id)
    audit("course_publish", f"v{c.version}", course_id=course_id)
    bus.publish("course", {"course_id": course_id, "active": True})
    return c


class CourseInUse(Exception):
    pass


def delete_course(course_id: int, force: bool = False) -> dict:
    """Delete a course and the survey recordings only it uses. Runs scored against it keep
    their results (times, check-ins, routes) but lose the link to the course map."""
    if get_setting("active_course_id") == course_id:
        raise CourseInUse("This is the active course. Make another course active (or none) in Admin first.")
    with session() as s:
        c = s.get(Course, course_id)
        if not c:
            raise KeyError("course not found")
        runs = s.exec(select(Run).where(Run.course_id == course_id)).all()
        if runs and not force:
            raise CourseInUse(f"{len(runs)} run(s) were scored against this course. They keep their results but "
                              "lose the course map. Delete anyway?")
        for r in runs:
            r.course_id = None
            s.add(r)
        files = s.exec(select(SurveyFile).where(SurveyFile.course_id == course_id)).all()
        survey_ids = {f.upload_id for f in files}
        for f in files:
            s.delete(f)
        bg = (c.data or {}).get("background") or {}
        name, version = c.name, c.version
        s.delete(c)
        s.commit()
        # Survey recordings no longer used by anything else are removed too
        removed = 0
        still_used = {f.upload_id for f in s.exec(select(SurveyFile)).all()}
        still_used |= {r.upload_id for r in s.exec(select(Run)).all() if r.upload_id}
        still_used |= {r.upload_id for r in s.exec(select(Recording)).all()}
        for uid in survey_ids - still_used:
            up = s.get(Upload, uid)
            if up:
                shutil.rmtree(dirs()["bundles"] / up.sha256[:16], ignore_errors=True)
                storage.delete(up.path)
                s.delete(up)
                removed += 1
        s.commit()
    storage.delete(bg.get("key"))
    _bundle.cache_clear()
    audit("course_delete", f"{name} v{version}; {len(runs)} run(s) unlinked; {removed} survey file(s) removed")
    bus.publish("course", {"course_id": course_id, "deleted": True})
    return {"deleted": course_id, "runs_unlinked": len(runs), "survey_files_removed": removed}


def new_version(course_id: int) -> Course:
    """Copy a published course into a new editable draft version."""
    with session() as s:
        c = s.get(Course, course_id)
        prev = s.exec(select(Course).where(Course.lineage == c.lineage)).all()
        files = s.exec(select(SurveyFile).where(SurveyFile.course_id == course_id)).all()
        n = Course(event_id=c.event_id, name=c.name, version=max(p.version for p in prev) + 1,
                   status="draft", lineage=c.lineage, data=json.loads(json.dumps(c.data)))
        s.add(n)
        s.commit()
        s.refresh(n)
        for f in files:
            s.add(SurveyFile(course_id=n.id, upload_id=f.upload_id))
        s.commit()
    return n


def set_background(course_id: int, filename: str, data: bytes) -> Course:
    ext = Path(filename).suffix.lower() or ".png"
    key = storage.put(f"background/course_{course_id}{ext}", data)
    with session() as s:
        c = s.get(Course, course_id)
        doc = json.loads(json.dumps(c.data))
        doc["background"] = {"key": key, "filename": filename, "pins": [], "transform": None}
        c.data = doc
        s.add(c)
        s.commit()
        s.refresh(c)
    return c


def set_pins(course_id: int, pins: list[dict], width: int | None, height: int | None) -> Course:
    with session() as s:
        c = s.get(Course, course_id)
        doc = json.loads(json.dumps(c.data))
    bg = doc.get("background") or {}
    bg["pins"] = pins
    if width:
        bg["width"], bg["height"] = width, height
    doc["background"] = bg
    _refit(doc)
    with session() as s:
        c = s.get(Course, course_id)
        c.data = doc
        s.add(c)
        s.commit()
        s.refresh(c)
    bus.publish("course", {"course_id": course_id})
    return c


def _refit(doc: dict) -> None:
    bg = doc["background"]
    pts = {s["id"]: (s["x"], s["y"]) for s in doc["stations"]}
    pts["BOOTH"] = (doc["booth"]["x"], doc["booth"]["y"])
    pins = [{"x": pts[p["station"]][0], "y": pts[p["station"]][1], "u": p["u"], "v": p["v"]}
            for p in bg.get("pins", []) if p.get("station") in pts]
    bg["transform"] = image_fit.fit(pins) if len(pins) >= 2 else None


# -- explorer -------------------------------------------------------------------

def create_recording(upload: Upload, title: str, description: str | None, profile: str,
                     in_library: bool, annotations: list | None = None, run_id: int | None = None) -> Recording:
    with session() as s:
        r = Recording(upload_id=upload.id, title=title, description=description, profile=profile,
                      in_library=in_library, annotations=annotations or [], run_id=run_id)
        s.add(r)
        s.commit()
        s.refresh(r)
    POOL.submit(_analyze_safe, r.id)
    return r


def _analyze_safe(rec_id: int) -> None:
    try:
        with session() as s:
            r = s.get(Recording, rec_id)
        b = bundle_for(r.upload_id)
        a = analyze(b, r.profile, r.annotations)
        if r.run_id:
            t = run_track(r.run_id)
            if t:
                a["track"] = t
                a["story"] = restory(b, a, r.profile, r.annotations)["story"]
        key = storage.put_json(f"analysis/rec_{rec_id}.json", a)
        for model in ("sensor", "quadcopter"):          # replay depends on the analysis
            storage.delete(f"analysis/rec_{rec_id}_replay_{model}.json")
        with session() as s:
            r = s.get(Recording, rec_id)
            r.status, r.analysis_path, r.error = "ready", key, None
            s.add(r)
            s.commit()
    except Exception as ex:
        log.exception("analysis failed")
        with session() as s:
            r = s.get(Recording, rec_id)
            r.status, r.error = "error", f"{type(ex).__name__}: {ex}"
            s.add(r)
            s.commit()
    bus.publish("recording", {"recording_id": rec_id})


def run_track(run_id: int) -> dict | None:
    """A hunt run's route fitted to its course, for the Explorer map and replay."""
    with session() as s:
        run = s.get(Run, run_id)
        course = s.get(Course, run.course_id) if run and run.course_id else None
    res = load_result(run) if run else None
    if not res or not (res.get("route") or {}).get("x"):
        return None
    rt = res["route"]
    d = (course.data or {}) if course else {}
    from ..position.projection import path_length
    return {"available": True, "source": "run", "t": rt["t"], "x": rt["x"], "y": rt["y"], "route_source": rt.get("source"),
            "distance_m": round(path_length(rt["x"], rt["y"]), 1), "run_id": run_id,
            "course": {"id": course.id, "stations": d.get("stations"), "booth": d.get("booth"),
                       "background": d.get("background"), "route": d.get("route")} if course else None,
            "visited": [c.get("station") for c in res.get("checkins", []) if c.get("station")],
            "note": "Route reconstructed from steps and heading, fitted to the course stations it checked in at."
                    if res.get("positioning_mode") == "dead_reckoning" else "Route from the hunt run."}


def ensure_run_recording(run_id: int) -> None:
    """Every returned hunt sensor shows up in Recording Explorer (no second upload)."""
    with session() as s:
        run = s.get(Run, run_id)
        p = s.get(Participant, run.participant_id) if run else None
        up = s.get(Upload, run.upload_id) if run and run.upload_id else None
        rec = s.exec(select(Recording).where(Recording.upload_id == run.upload_id)).first() if up else None
    if not up:
        return
    if rec is None:
        create_recording(up, f"{p.display_name if p else 'Participant'}: hunt run",
                         f"Scavenger hunt run, sensor {run.sensor_serial}.", "hunt", False, run_id=run_id)
    else:
        if rec.run_id != run_id:
            with session() as s:
                r = s.get(Recording, rec.id)
                r.run_id = run_id
                s.add(r)
                s.commit()
        POOL.submit(_analyze_safe, rec.id)      # route may have changed (overrides, rescore)


def recording_analysis(rec: Recording) -> dict | None:
    return storage.get_json(rec.analysis_path)


def recording_replay(rec: Recording) -> dict:
    """Reconstructed replay track, computed on first request and cached per profile model."""
    from ..explorer.profiles import get_profile
    from ..explorer.replay import build_replay
    model = get_profile(rec.profile).get("replay_model", "sensor")
    key = f"analysis/rec_{rec.id}_replay_{model}.json"
    cached = storage.get_json(key)
    if cached is not None:
        return cached
    r = build_replay(bundle_for(rec.upload_id), recording_analysis(rec), model)
    storage.put_json(key, r)
    return r


def update_recording(rec_id: int, patch: dict) -> Recording:
    with session() as s:
        r = s.get(Recording, rec_id)
        for k in ("title", "description", "profile", "annotations", "in_library"):
            if k in patch:
                setattr(r, k, patch[k])
        s.add(r)
        s.commit()
        s.refresh(r)
    if ("profile" in patch or "annotations" in patch) and r.analysis_path:
        a = recording_analysis(r)
        a = restory(bundle_for(r.upload_id), a, r.profile, r.annotations)
        storage.put_json(r.analysis_path, a)
    bus.publish("recording", {"recording_id": rec_id})
    return r


def seed_library() -> None:
    """Load the drone flight into the Demo Library on first start."""
    from ..config import REPO_ROOT
    src = REPO_ROOT / "fixtures" / "Drone_Flight.IDE"
    if not src.exists():
        return
    sha = sha256_file(src)
    with session() as s:
        up = s.exec(select(Upload).where(Upload.sha256 == sha)).first()
        if up:
            if s.exec(select(Recording).where(Recording.upload_id == up.id)).first():
                return
    up = ingest_file(src, "Drone_Flight.IDE")
    if up.status != "parsed":
        return
    create_recording(up, "Drone flight", "A drone flight recorded by an enDAQ S4 sensor: a climb of about 35 m, "
                     "propeller vibration, rotation and the largest shock event. The sensor was enclosed, so light "
                     "reads zero.", "drone", True)


# -- admin ----------------------------------------------------------------------

def reset_event(new_name: str | None = None) -> None:
    """Delete participants, runs, results and GPS tracks for the current event; start a new one."""
    ev = current_event()
    with session() as s:
        runs = s.exec(select(Run).where(Run.event_id == ev.id)).all()
        for r in runs:
            storage.delete(r.result_path)
            for sc in s.exec(select(Scan).where(Scan.run_id == r.id)).all():
                s.delete(sc)
            s.delete(r)
        for p in s.exec(select(Participant).where(Participant.event_id == ev.id)).all():
            s.delete(p)
        for a in s.exec(select(AuditLog).where(AuditLog.run_id != None)).all():  # noqa: E711
            s.delete(a)
        # participant uploads (not surveys, not explorer recordings) are removed too
        keep = {f.upload_id for f in s.exec(select(SurveyFile)).all()}
        keep |= {r.upload_id for r in s.exec(select(Recording)).all()}
        for up in s.exec(select(Upload)).all():
            if up.id not in keep:
                shutil.rmtree(dirs()["bundles"] / up.sha256[:16], ignore_errors=True)
                storage.delete(up.path)
                s.delete(up)
        ev.active = False
        s.add(ev)
        s.commit()
    _bundle.cache_clear()
    with session() as s:
        from .db import Event
        s.add(Event(name=new_name or ev.name))
        s.commit()
    bus.publish("reset", {})
    bus.publish("leaderboard", {})
