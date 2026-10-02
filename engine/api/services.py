"""Orchestration: uploads, run processing, courses, explorer recordings."""
from __future__ import annotations

import json
import logging
import shutil
import threading
import traceback
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


def ingest_file(path: Path, filename: str | None = None, source_path: str | None = None) -> Upload:
    """Hash, store and parse a recording. Re-uploading the same file returns the existing row."""
    filename = filename or path.name
    sha = sha256_file(path)
    with _ingest_lock:
        with session() as s:
            existing = s.exec(select(Upload).where(Upload.sha256 == sha)).first()
            if existing and existing.status == "parsed":
                return existing
        ext = _ext(filename)
        key = f"upload/{sha[:16]}{ext}"
        if not storage.exists(key):
            storage.put(key, path.read_bytes())       # the original is what survives restarts
        up = existing or Upload(sha256=sha, filename=filename, size=path.stat().st_size, path=key,
                                source_path=source_path)
        up.path = key
        try:
            b = _build_bundle(key, sha)
            m = b.meta
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


def _ext(filename: str) -> str:
    return ".synth.zip" if filename.lower().endswith(".zip") else Path(filename).suffix.lower() or ".ide"


def _build_bundle(key: str, sha: str) -> Bundle:
    """Parse the stored original into the local bundle cache."""
    bdir = dirs()["bundles"] / sha[:16]
    if key.endswith(".synth.zip"):
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
                     in_library: bool, annotations: list | None = None) -> Recording:
    with session() as s:
        r = Recording(upload_id=upload.id, title=title, description=description, profile=profile,
                      in_library=in_library, annotations=annotations or [])
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
        key = storage.put_json(f"analysis/rec_{rec_id}.json", analyze(b, r.profile, r.annotations))
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
