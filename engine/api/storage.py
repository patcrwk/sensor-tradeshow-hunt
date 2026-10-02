"""Durable storage for originals and derived documents.

Hosted mode (DATABASE_URL set): bytes live in the Blob table, because Heroku's
filesystem is wiped on every deploy and restart. Booth mode: plain files under
data/blobs. Callers use keys such as "upload/<sha>.IDE" or "result/run_12.json".

The local disk is still used as a cache (parsed recording bundles); anything
missing from the cache is rebuilt from the stored original on demand.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import select

from ..config import data_dir
from .db import Blob, is_postgres, session


def _hosted() -> bool:
    return is_postgres()


def _file(key: str) -> Path:
    p = data_dir() / "blobs" / key
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


_json_cache: dict[str, object] = {}


def put(key: str, data: bytes) -> str:
    _json_cache.pop(key, None)
    if _hosted():
        with session() as s:
            row = s.get(Blob, key)
            if row is None:
                row = Blob(key=key, data=data, size=len(data))
            else:
                row.data, row.size = data, len(data)
            s.add(row)
            s.commit()
    else:
        _file(key).write_bytes(data)
    return key


def get(key: str | None) -> bytes | None:
    if not key:
        return None
    if key.startswith("/"):                     # older booth databases stored file paths
        p = Path(key)
        return p.read_bytes() if p.exists() else None
    if _hosted():
        with session() as s:
            row = s.get(Blob, key)
            return bytes(row.data) if row else None
    p = _file(key)
    return p.read_bytes() if p.exists() else None


def exists(key: str | None) -> bool:
    if not key:
        return False
    if key.startswith("/"):
        return Path(key).exists()
    if _hosted():
        with session() as s:
            return s.exec(select(Blob.key).where(Blob.key == key)).first() is not None
    return _file(key).exists()


def delete(key: str | None) -> None:
    if not key:
        return
    _json_cache.pop(key, None)
    if key.startswith("/"):
        Path(key).unlink(missing_ok=True)
        return
    if _hosted():
        with session() as s:
            row = s.get(Blob, key)
            if row:
                s.delete(row)
                s.commit()
    else:
        _file(key).unlink(missing_ok=True)


def put_json(key: str, obj) -> str:
    return put(key, json.dumps(obj, default=str).encode())


def get_json(key: str | None):
    """Parsed JSON, cached in memory (one engine process; put() invalidates)."""
    if not key:
        return None
    if key in _json_cache:
        return _json_cache[key]
    b = get(key)
    obj = json.loads(b) if b is not None else None
    if obj is not None:
        if len(_json_cache) > 64:
            _json_cache.clear()
        _json_cache[key] = obj
    return obj


def to_local(key: str, path: Path) -> Path | None:
    """Materialize a stored blob as a local file (for parsers that need a path)."""
    if path.exists():
        return path
    b = get(key)
    if b is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b)
    return path
