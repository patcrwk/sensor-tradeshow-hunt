"""Database via SQLModel: Postgres when DATABASE_URL is set (Heroku), else SQLite.

Tables hold identity, status and summary numbers. Large derived documents
(course geometry, run results, explorer analysis) are JSON: the course
document lives in Course.data; run results, explorer analyses, original
uploads and images go through storage.py (database blobs on Heroku, files
on the booth laptop), so the UI never touches raw data.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from typing import Any, Optional

from sqlalchemy import Column, inspect, text
from sqlalchemy.types import JSON, LargeBinary
from sqlmodel import Field, Session, SQLModel, create_engine, select

from ..config import data_dir

_engine = None


def now() -> float:
    return time.time()


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "Trade show"
    created_at: float = Field(default_factory=now)
    active: bool = True


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))


class Upload(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sha256: str = Field(index=True, unique=True)
    filename: str
    size: Optional[int] = None
    path: str                      # stored original
    bundle_dir: Optional[str] = None
    status: str = "pending"        # pending | parsed | error
    error: Optional[str] = None
    serial: Optional[str] = Field(default=None, index=True)
    model: Optional[str] = None
    start_epoch: Optional[float] = None
    duration_s: Optional[float] = None
    has_gps: bool = False
    synthetic: bool = False
    source_path: Optional[str] = None   # where it was found (watch folder)
    created_at: float = Field(default_factory=now)


class Sensor(SQLModel, table=True):
    serial: str = Field(primary_key=True)
    model: Optional[str] = None
    has_gps: Optional[bool] = None
    last_seen: Optional[float] = None


class Participant(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(index=True)
    display_name: str
    company: Optional[str] = None
    email: Optional[str] = None
    consent: bool = False
    created_at: float = Field(default_factory=now)


class Course(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(index=True)
    name: str
    version: int = 1
    status: str = "draft"          # draft | published | archived | needs_review
    lineage: Optional[int] = None  # first course id of this course's version chain
    data: Any = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    created_at: float = Field(default_factory=now)
    published_at: Optional[float] = None


class SurveyFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    course_id: int = Field(index=True)
    upload_id: int


class Run(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(index=True)
    token: Optional[str] = Field(default=None, index=True)   # participant phone link (QR)
    participant_id: int
    sensor_serial: str = Field(index=True)
    checkout_epoch: float = Field(default_factory=now)
    status: str = "out"            # out | processing | needs_review | published | error
    upload_id: Optional[int] = None
    course_id: Optional[int] = None
    course_version: Optional[int] = None
    positioning_mode: Optional[str] = None
    result_path: Optional[str] = None
    elapsed_s: Optional[float] = None
    complete: bool = False
    summary: Any = Field(default=None, sa_column=Column(JSON))
    overrides: Any = Field(default=None, sa_column=Column(JSON))
    error: Optional[str] = None
    processed_at: Optional[float] = None
    published_at: Optional[float] = None


class Scan(SQLModel, table=True):
    """A participant's phone scanned a station QR code."""
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    course_id: Optional[int] = None
    station: str                   # station id, or BOOTH
    at: float = Field(default_factory=now)   # server time (epoch seconds)


class Blob(SQLModel, table=True):
    """Binary storage for hosted mode (Heroku's disk is wiped on restart)."""
    key: str = Field(primary_key=True)
    data: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    size: int = 0
    created_at: float = Field(default_factory=now)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[int] = Field(default=None, index=True)
    course_id: Optional[int] = None
    at: float = Field(default_factory=now)
    action: str
    note: Optional[str] = None
    data: Any = Field(default=None, sa_column=Column(JSON))


class Recording(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    upload_id: int
    title: str
    description: Optional[str] = None
    profile: str = "generic"
    annotations: Any = Field(default=None, sa_column=Column(JSON))
    in_library: bool = False
    status: str = "processing"     # processing | ready | error
    analysis_path: Optional[str] = None
    error: Optional[str] = None
    created_at: float = Field(default_factory=now)


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):           # Heroku's form; SQLAlchemy wants postgresql+psycopg
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url or f"sqlite:///{data_dir() / 'demo.sqlite'}"


def is_postgres() -> bool:
    return database_url().startswith("postgresql")


def engine():
    global _engine
    if _engine is None:
        url = database_url()
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
        SQLModel.metadata.create_all(_engine)
        _add_missing_columns(_engine)
    return _engine


def _add_missing_columns(eng) -> None:
    """Tiny migration: add columns introduced after a database was created (all nullable)."""
    insp = inspect(eng)
    for table in SQLModel.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl = col.type.compile(dialect=eng.dialect)
            with eng.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


def reset_engine():
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


@contextmanager
def session():
    with Session(engine(), expire_on_commit=False) as s:
        yield s


def get_setting(key: str, default=None):
    with session() as s:
        row = s.get(Setting, key)
        return row.value if row is not None else default


def set_setting(key: str, value) -> None:
    with session() as s:
        row = s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value=value))
        else:
            row.value = json.loads(json.dumps(value))
            s.add(row)
        s.commit()


def current_event() -> Event:
    with session() as s:
        ev = s.exec(select(Event).where(Event.active == True)).first()  # noqa: E712
        if ev is None:
            ev = Event(name=get_setting("branding", {}).get("event_name", "Trade show"))
            s.add(ev)
            s.commit()
            s.refresh(ev)
        return ev


def audit(action: str, note: str | None = None, run_id: int | None = None, course_id: int | None = None,
          data=None) -> None:
    with session() as s:
        s.add(AuditLog(action=action, note=note, run_id=run_id, course_id=course_id, data=data))
        s.commit()
