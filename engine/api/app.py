"""FastAPI application: hunt, courses, explorer, display, admin."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlmodel import select

from ..config import REPO_ROOT, get_config
from ..course.package import export_package, read_package
from ..explorer.profiles import list_profiles
from ..explorer.timeseries import window
from ..hunt import scoring
from ..hunt.crowd import crowd_stats
from . import bus, services as S, watcher
from .db import (AuditLog, Course, Participant, Recording, Run, Sensor, SurveyFile, Upload, audit,
                 current_event, get_setting, now, session, set_setting)

log = logging.getLogger("engine")

DEFAULT_BRANDING = {"event_name": "enDAQ Sensor Scavenger Hunt", "company": "enDAQ",
                    "primary": "#00a3e0", "accent": "#ffb000", "logo_url": None,
                    "tagline": "Every number on this screen was measured by the sensor."}
DEFAULT_KIOSK = {"panels": ["leaderboard:fastest", "course", "leaderboard:efficient", "crowd", "leaderboard:crew",
                            "heatmap", "leaderboard:steady", "environment", "story:library"],
                 "seconds_per_panel": 15, "story_recording_ids": []}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    bus.bind_loop(asyncio.get_running_loop())
    current_event()
    if get_setting("branding") is None:
        set_setting("branding", DEFAULT_BRANDING)
    if get_setting("kiosk") is None:
        set_setting("kiosk", DEFAULT_KIOSK)
    if get_setting("watch_folder") is None:
        set_setting("watch_folder", get_config().paths.watch_folder or "")
    if os.environ.get("ENGINE_NO_BACKGROUND") != "1":
        watcher.start()
        S.POOL.submit(S.seed_library)
    yield
    watcher.stop()


app = FastAPI(title="enDAQ Sensor Demo Engine", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _404(what="not found"):
    raise HTTPException(404, what)


# -- health / stream ------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "event": current_event().name, "active_course_id": get_setting("active_course_id"),
            "watcher": watcher.state}


@app.get("/api/stream")
async def stream():
    q = bus.subscribe()

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# -- settings -------------------------------------------------------------------

@app.get("/api/settings")
def settings():
    return {"branding": get_setting("branding", DEFAULT_BRANDING), "kiosk": get_setting("kiosk", DEFAULT_KIOSK),
            "watch_folder": get_setting("watch_folder", ""), "auto_publish": get_setting("auto_publish", True),
            "active_course_id": get_setting("active_course_id"), "event": current_event().model_dump(),
            "sensor_data_subdir": get_config().paths.sensor_data_subdir}


class SettingsPatch(BaseModel):
    branding: dict | None = None
    kiosk: dict | None = None
    watch_folder: str | None = None
    auto_publish: bool | None = None
    active_course_id: int | None = None
    event_name: str | None = None


@app.put("/api/settings")
def put_settings(p: SettingsPatch):
    for k in ("branding", "kiosk", "watch_folder", "auto_publish"):
        v = getattr(p, k)
        if v is not None:
            set_setting(k, v)
    if p.active_course_id is not None:
        set_setting("active_course_id", p.active_course_id or None)
    if p.event_name:
        ev = current_event()
        with session() as s:
            e = s.get(type(ev), ev.id)
            e.name = p.event_name
            s.add(e)
            s.commit()
    bus.publish("settings", {})
    return settings()


# -- uploads --------------------------------------------------------------------

def _upload_dict(u: Upload) -> dict:
    d = u.model_dump(exclude={"path", "bundle_dir"})
    return d


@app.post("/api/uploads")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    up = await asyncio.to_thread(S.ingest_bytes, file.filename or "upload.IDE", data)
    bus.publish("upload", {"upload_id": up.id})
    return {"upload": _upload_dict(up), "candidates": S.upload_candidates(up) if up.status == "parsed" else [],
            "attached_run": _run_for_upload(up.id)}


def _run_for_upload(upload_id: int):
    with session() as s:
        r = s.exec(select(Run).where(Run.upload_id == upload_id)).first()
        return r.id if r else None


@app.get("/api/uploads/pending")
def pending_uploads():
    """Participant-looking uploads in this event not yet attached to a run (for the returns screen)."""
    ev = current_event()
    with session() as s:
        ups = s.exec(select(Upload).where(Upload.created_at >= ev.created_at).order_by(Upload.id.desc())).all()
        used = {r.upload_id for r in s.exec(select(Run)).all() if r.upload_id}
        used |= {f.upload_id for f in s.exec(select(SurveyFile)).all()}
        used |= {r.upload_id for r in s.exec(select(Recording)).all()}
    out = []
    for u in ups:
        if u.id in used:
            continue
        out.append({"upload": _upload_dict(u), "candidates": S.upload_candidates(u) if u.status == "parsed" else []})
    return out


@app.get("/api/uploads/{upload_id}")
def get_upload(upload_id: int):
    with session() as s:
        u = s.get(Upload, upload_id)
    if not u:
        _404()
    return {"upload": _upload_dict(u), "candidates": S.upload_candidates(u) if u.status == "parsed" else [],
            "attached_run": _run_for_upload(u.id)}


@app.delete("/api/uploads/{upload_id}/source")
def clear_source(upload_id: int, confirm: bool = Query(False)):
    """Delete the original file from the sensor (watch folder) after processing."""
    if not confirm:
        raise HTTPException(400, "confirmation required")
    with session() as s:
        u = s.get(Upload, upload_id)
    if not u or not u.source_path:
        raise HTTPException(400, "this upload did not come from the watch folder")
    p = Path(u.source_path)
    if p.exists():
        p.unlink()
    audit("clear_sensor_file", u.source_path)
    return {"deleted": u.source_path}


# -- sensors / check-out --------------------------------------------------------

@app.get("/api/sensors")
def sensors():
    with session() as s:
        rows = s.exec(select(Sensor)).all()
        out_runs = s.exec(select(Run).where(Run.status == "out", Run.event_id == current_event().id)).all()
    busy = {r.sensor_serial for r in out_runs}
    return [{**r.model_dump(), "checked_out": r.serial in busy} for r in rows]


@app.get("/api/sensors/{serial}/status")
def sensor_status(serial: str):
    with session() as s:
        sen = s.get(Sensor, serial)
    return {"serial": serial, "known": sen is not None, "has_gps": sen.has_gps if sen else None,
            "gps_fix": None,
            "message": "Live GPS fix status cannot be read over USB. Power the sensor on and wait for a GPS fix "
                       "(a minute or more from cold) before handing it out."}


class Checkout(BaseModel):
    display_name: str
    serial: str
    company: str | None = None
    email: str | None = None
    consent: bool = False


@app.post("/api/runs/checkout")
def checkout(c: Checkout):
    if not c.display_name.strip() or not c.serial.strip():
        raise HTTPException(400, "name and sensor serial are required")
    ev = current_event()
    with session() as s:
        busy = s.exec(select(Run).where(Run.event_id == ev.id, Run.status == "out",
                                        Run.sensor_serial == c.serial.strip())).first()
        p = Participant(event_id=ev.id, display_name=c.display_name.strip()[:40],
                        company=(c.company or None) if c.consent else None,
                        email=(c.email or None) if c.consent else None, consent=c.consent)
        s.add(p)
        s.commit()
        s.refresh(p)
        r = Run(event_id=ev.id, participant_id=p.id, sensor_serial=c.serial.strip())
        s.add(r)
        s.commit()
        s.refresh(r)
        if not s.get(Sensor, r.sensor_serial):
            s.add(Sensor(serial=r.sensor_serial))
            s.commit()
    bus.publish("run", {"run_id": r.id, "status": "out"})
    warn = f"sensor {c.serial} was already checked out (run {busy.id}); both runs stay open" if busy else None
    return {"run": _run_row(r, p), "warning": warn}


# -- runs -----------------------------------------------------------------------

def _run_row(r: Run, p: Participant | None, private: bool = True) -> dict:
    d = {"id": r.id, "name": p.display_name if p else "?", "serial": r.sensor_serial, "status": r.status,
         "checkout_epoch": r.checkout_epoch, "upload_id": r.upload_id, "course_id": r.course_id,
         "course_version": r.course_version, "elapsed_s": r.elapsed_s, "complete": r.complete,
         "positioning_mode": r.positioning_mode, "summary": r.summary, "error": r.error,
         "processed_at": r.processed_at, "published_at": r.published_at,
         "has_overrides": bool(r.overrides)}
    if private and p:
        d["company"] = p.company
    return d


@app.get("/api/runs")
def runs(status: str | None = None):
    ev = current_event()
    with session() as s:
        q = select(Run, Participant).where(Run.event_id == ev.id, Run.participant_id == Participant.id)
        if status:
            q = q.where(Run.status.in_(status.split(",")))
        rows = s.exec(q.order_by(Run.id.desc())).all()
    return [_run_row(r, p) for r, p in rows]


@app.get("/api/runs/{run_id}")
def run_detail(run_id: int):
    with session() as s:
        r = s.get(Run, run_id)
        if not r:
            _404()
        p = s.get(Participant, r.participant_id)
        logs = s.exec(select(AuditLog).where(AuditLog.run_id == run_id).order_by(AuditLog.id)).all()
        up = s.get(Upload, r.upload_id) if r.upload_id else None
    return {"run": _run_row(r, p), "result": S.load_result(r), "overrides": r.overrides,
            "audit": [a.model_dump() for a in logs], "upload": _upload_dict(up) if up else None}


class Attach(BaseModel):
    upload_id: int


@app.post("/api/runs/{run_id}/attach")
def attach(run_id: int, a: Attach):
    r = S.attach_upload(run_id, a.upload_id)
    return {"run_id": r.id, "status": r.status}


class Overrides(BaseModel):
    checkins: list[dict] | None
    note: str


@app.put("/api/runs/{run_id}/checkins")
def put_checkins(run_id: int, o: Overrides):
    if not o.note.strip():
        raise HTTPException(400, "an audit note is required")
    r = S.set_overrides(run_id, o.checkins, o.note)
    return {"run_id": r.id, "status": r.status}


class Note(BaseModel):
    note: str | None = None


@app.post("/api/runs/{run_id}/publish")
def publish(run_id: int, n: Note | None = None):
    return {"status": S.publish_run(run_id, True, n.note if n else None).status}


@app.post("/api/runs/{run_id}/unpublish")
def unpublish(run_id: int, n: Note | None = None):
    return {"status": S.publish_run(run_id, False, n.note if n else None).status}


@app.post("/api/runs/{run_id}/reprocess")
def reprocess(run_id: int):
    S.POOL.submit(S._process_safe, run_id)
    return {"queued": True}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: int):
    with session() as s:
        r = s.get(Run, run_id)
        if not r:
            _404()
        if r.status != "out":
            raise HTTPException(400, "only open check-outs can be cancelled; unpublish instead")
        s.delete(r)
        s.commit()
    audit("cancel_checkout", run_id=run_id)
    bus.publish("run", {"run_id": run_id, "status": "deleted"})
    return {"deleted": run_id}


@app.get("/api/runs/{run_id}/ghost")
def ghost(run_id: int, vs: str = "leader"):
    """Route of the current leader, or the crew survey, for a side-by-side replay."""
    if vs == "crew":
        c = S.active_course()
        if not c or not c.data:
            _404("no active course")
        return {"name": "Crew", "route": c.data["route"], "par_s": c.data["par"]["par_time_s"]}
    lb = scoring.leaderboard(_published_rows(), "fastest", 1)
    if not lb:
        _404("no leader yet")
    with session() as s:
        r = s.get(Run, lb[0]["run_id"])
    res = S.load_result(r)
    return {"name": lb[0]["name"], "route": res["route"], "start": res["start"], "elapsed_s": res["elapsed_s"]}


# -- leaderboard / display ------------------------------------------------------

def _published_rows(with_result: bool = False) -> list[dict]:
    ev = current_event()
    with session() as s:
        rows = s.exec(select(Run, Participant).where(Run.event_id == ev.id, Run.status == "published",
                                                     Run.participant_id == Participant.id)).all()
    out = []
    for r, p in rows:
        d = {"run_id": r.id, "name": p.display_name, "summary": r.summary or {}}
        if with_result:
            d["result"] = S.load_result(r)
        out.append(d)
    return out


@app.get("/api/leaderboard")
def leaderboard(category: str = "fastest", limit: int = 10):
    if category not in scoring.CATEGORIES:
        raise HTTPException(400, f"unknown category; one of {list(scoring.CATEGORIES)}")
    return {"category": category, **scoring.CATEGORIES[category],
            "rows": scoring.leaderboard(_published_rows(), category, limit)}


@app.get("/api/leaderboards")
def leaderboards(limit: int = 10):
    rows = _published_rows()
    return {k: {**v, "rows": scoring.leaderboard(rows, k, limit)} for k, v in scoring.CATEGORIES.items()}


@app.get("/api/dashboard")
def dashboard():
    c = S.active_course()
    return crowd_stats(_published_rows(with_result=True), c.data if c else None)


# -- courses --------------------------------------------------------------------

def _course_dict(c: Course, full: bool = True) -> dict:
    d = {"id": c.id, "name": c.name, "version": c.version, "status": c.status, "lineage": c.lineage,
         "error": c.error, "created_at": c.created_at, "published_at": c.published_at,
         "active": get_setting("active_course_id") == c.id}
    if full:
        d["data"] = c.data
        with session() as s:
            files = s.exec(select(SurveyFile).where(SurveyFile.course_id == c.id)).all()
            ups = [s.get(Upload, f.upload_id) for f in files]
        d["surveys"] = [_upload_dict(u) for u in ups if u]
    elif c.data:
        d["stations"] = len(c.data.get("stations", []))
        d["mode"] = c.data.get("positioning_mode")
        d["quality"] = c.data.get("quality", {}).get("level")
    return d


@app.get("/api/courses")
def courses():
    with session() as s:
        rows = s.exec(select(Course).order_by(Course.id.desc())).all()
    return [_course_dict(c, full=False) for c in rows]


@app.get("/api/courses/active")
def course_active():
    c = S.active_course()
    return _course_dict(c) if c else None


@app.post("/api/courses/survey")
async def course_from_survey(files: list[UploadFile] = File(...), name: str = Form("Course"),
                             mode: str | None = Form(None), lineage: int | None = Form(None)):
    ids = []
    for f in files:
        up = await asyncio.to_thread(S.ingest_bytes, f.filename or "survey.IDE", await f.read())
        if up.status != "parsed":
            raise HTTPException(400, f"{f.filename}: {up.error}")
        ids.append(up.id)
    c = await asyncio.to_thread(S.create_course, name, ids, mode or None, lineage)
    return _course_dict(c)


@app.get("/api/courses/{course_id}")
def course(course_id: int):
    with session() as s:
        c = s.get(Course, course_id)
    if not c:
        _404()
    return _course_dict(c)


@app.patch("/api/courses/{course_id}")
def patch_course(course_id: int, patch: dict):
    return _course_dict(S.edit_course(course_id, patch))


class Rederive(BaseModel):
    mode: str | None = None


@app.post("/api/courses/{course_id}/rederive")
def rederive(course_id: int, r: Rederive):
    return _course_dict(S.derive(course_id, r.mode))


@app.post("/api/courses/{course_id}/publish")
def publish_course(course_id: int):
    try:
        c = S.publish_course(course_id)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    ev = current_event()
    with session() as s:
        n = len(s.exec(select(Run).where(Run.event_id == ev.id, Run.upload_id != None)).all())  # noqa: E711
    return {**_course_dict(c), "runs_to_rescore": n}


@app.post("/api/courses/{course_id}/rescore")
def rescore(course_id: int):
    return {"queued": S.rescore_all(course_id)}


@app.post("/api/courses/{course_id}/new-version")
def course_new_version(course_id: int):
    return _course_dict(S.new_version(course_id))


@app.post("/api/courses/{course_id}/surveys")
async def add_survey(course_id: int, files: list[UploadFile] = File(...)):
    for f in files:
        up = await asyncio.to_thread(S.ingest_bytes, f.filename or "survey.IDE", await f.read())
        if up.status != "parsed":
            raise HTTPException(400, f"{f.filename}: {up.error}")
        with session() as s:
            s.add(SurveyFile(course_id=course_id, upload_id=up.id))
            s.commit()
    return _course_dict(await asyncio.to_thread(S.derive, course_id, None))


@app.post("/api/courses/{course_id}/background")
async def background(course_id: int, file: UploadFile = File(...)):
    return _course_dict(S.set_background(course_id, file.filename or "map.png", await file.read()))


@app.get("/api/courses/{course_id}/background")
def get_background(course_id: int):
    with session() as s:
        c = s.get(Course, course_id)
    bg = (c.data or {}).get("background") if c else None
    if not bg or not Path(bg["path"]).exists():
        _404()
    return FileResponse(bg["path"])


class Pins(BaseModel):
    pins: list[dict]
    width: int | None = None
    height: int | None = None


@app.put("/api/courses/{course_id}/pins")
def pins(course_id: int, p: Pins):
    try:
        return _course_dict(S.set_pins(course_id, p.pins, p.width, p.height))
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.get("/api/courses/{course_id}/export")
def export_course(course_id: int):
    with session() as s:
        c = s.get(Course, course_id)
        files = s.exec(select(SurveyFile).where(SurveyFile.course_id == course_id)).all()
        ups = [s.get(Upload, f.upload_id) for f in files]
    if not c:
        _404()
    bg = Path(c.data["background"]["path"]) if c.data and c.data.get("background") else None
    data = export_package({"name": c.name, "version": c.version, "status": c.status}, c.data or {},
                          [Path(u.path) for u in ups], bg)
    fname = f"course_{c.name.replace(' ', '_')}_v{c.version}.zip"
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@app.post("/api/courses/import")
async def import_course(file: UploadFile = File(...)):
    try:
        pkg = read_package(await file.read())
    except Exception as ex:
        raise HTTPException(400, f"not a course package: {ex}")
    ev = current_event()
    ids = []
    for name, data in pkg["surveys"].items():
        up = await asyncio.to_thread(S.ingest_bytes, name, data)
        ids.append(up.id)
    doc = pkg["course"]
    with session() as s:
        c = Course(event_id=ev.id, name=pkg["manifest"]["course"]["name"] + " (imported)", status="draft",
                   version=1, data=doc)
        s.add(c)
        s.commit()
        s.refresh(c)
        c.lineage = c.id
        s.add(c)
        for uid in ids:
            s.add(SurveyFile(course_id=c.id, upload_id=uid))
        s.commit()
        s.refresh(c)
    if pkg["background"]:
        name, data = pkg["background"]
        S.set_background(c.id, name, data)
        if doc.get("background", {}).get("pins"):
            S.set_pins(c.id, doc["background"]["pins"], doc["background"].get("width"), doc["background"].get("height"))
    with session() as s:
        c = s.get(Course, c.id)
    audit("course_import", file.filename, course_id=c.id)
    return _course_dict(c)


# -- explorer -------------------------------------------------------------------

def _rec_dict(r: Recording) -> dict:
    with session() as s:
        u = s.get(Upload, r.upload_id)
    return {**r.model_dump(exclude={"analysis_path"}), "upload": _upload_dict(u) if u else None}


@app.get("/api/profiles")
def profiles():
    return list_profiles()


@app.get("/api/recordings")
def recordings(library: bool | None = None):
    with session() as s:
        q = select(Recording).order_by(Recording.id.desc())
        if library is not None:
            q = q.where(Recording.in_library == library)
        rows = s.exec(q).all()
    return [_rec_dict(r) for r in rows]


@app.post("/api/recordings")
async def new_recording(file: UploadFile = File(...), title: str = Form(""), description: str = Form(""),
                        profile: str = Form("generic"), in_library: bool = Form(False)):
    up = await asyncio.to_thread(S.ingest_bytes, file.filename or "recording.IDE", await file.read())
    if up.status != "parsed":
        raise HTTPException(400, up.error or "could not read file")
    with session() as s:
        existing = s.exec(select(Recording).where(Recording.upload_id == up.id)).first()
    if existing:
        return _rec_dict(existing)
    r = S.create_recording(up, title or Path(up.filename).stem, description or None, profile, in_library)
    return _rec_dict(r)


@app.get("/api/recordings/{rec_id}")
def recording(rec_id: int):
    with session() as s:
        r = s.get(Recording, rec_id)
    if not r:
        _404()
    return _rec_dict(r)


@app.get("/api/recordings/{rec_id}/analysis")
def recording_analysis(rec_id: int, part: str | None = None):
    with session() as s:
        r = s.get(Recording, rec_id)
    if not r:
        _404()
    a = S.recording_analysis(r)
    if a is None:
        raise HTTPException(409, "analysis not ready")
    if part:
        return a.get(part)
    return {k: v for k, v in a.items() if k not in ("frequency",)} | {"frequency_ready": True}


@app.get("/api/recordings/{rec_id}/timeseries")
def recording_ts(rec_id: int, ch: str, t0: float | None = None, t1: float | None = None, n: int = 1500):
    with session() as s:
        r = s.get(Recording, rec_id)
    if not r:
        _404()
    b = S.bundle_for(r.upload_id)
    try:
        return window(b, ch, t0, t1, min(max(n, 50), 5000))
    except (KeyError, FileNotFoundError):
        _404("channel not found")


@app.patch("/api/recordings/{rec_id}")
def patch_recording(rec_id: int, patch: dict):
    return _rec_dict(S.update_recording(rec_id, patch))


@app.post("/api/recordings/{rec_id}/reanalyze")
def reanalyze(rec_id: int):
    S.POOL.submit(S._analyze_safe, rec_id)
    return {"queued": True}


@app.delete("/api/recordings/{rec_id}")
def delete_recording(rec_id: int):
    with session() as s:
        r = s.get(Recording, rec_id)
        if not r:
            _404()
        s.delete(r)
        s.commit()
    return {"deleted": rec_id}


# -- admin ----------------------------------------------------------------------

@app.get("/api/admin/leads.csv")
def leads():
    ev = current_event()
    with session() as s:
        rows = s.exec(select(Participant).where(Participant.event_id == ev.id, Participant.consent == True)).all()  # noqa: E712
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["display_name", "company", "email", "checked_out_at"])
    import datetime as dt
    for p in rows:
        w.writerow([p.display_name, p.company or "", p.email or "",
                    dt.datetime.fromtimestamp(p.created_at).isoformat(timespec="seconds")])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="leads.csv"'})


class Reset(BaseModel):
    confirm: str
    new_event_name: str | None = None


@app.post("/api/admin/reset")
def reset(r: Reset):
    if r.confirm != "RESET":
        raise HTTPException(400, 'type RESET to confirm')
    S.reset_event(r.new_event_name)
    return {"ok": True, "event": current_event().model_dump()}


@app.post("/api/admin/watch/scan")
def watch_scan():
    return {"new": watcher.scan_once(), "state": watcher.state}


class SynthReq(BaseModel):
    kind: str = "participant"        # participant | survey | set
    gps_profile: str = "outdoor"
    use_holders: bool = False
    use_taps: bool = False
    serial: int = 90001
    seed: int = 1


@app.post("/api/admin/synthetic")
def synthetic(req: SynthReq):
    """Generate synthetic test files into fixtures/synthetic for UI testing."""
    from ..synthetic import cli
    out = cli.generate_set(REPO_ROOT / "fixtures" / "synthetic", gps_profile=req.gps_profile,
                           use_holders=req.use_holders, use_taps=req.use_taps, serial=req.serial,
                           seed=req.seed, n_participants=3 if req.kind == "set" else (1 if req.kind == "participant" else 0),
                           survey=req.kind in ("survey", "set"))
    return {"files": [str(p.relative_to(REPO_ROOT)) for p in out]}


@app.get("/api/admin/synthetic/{name}")
def synthetic_file(name: str):
    p = REPO_ROOT / "fixtures" / "synthetic" / Path(name).name
    if not p.exists():
        _404()
    return FileResponse(p, filename=p.name)


@app.get("/api/admin/audit")
def audit_log(limit: int = 100):
    with session() as s:
        rows = s.exec(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return [a.model_dump() for a in rows]
