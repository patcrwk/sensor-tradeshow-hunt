"""Tiny in-process pub/sub for Server-Sent Events."""
from __future__ import annotations

import asyncio
import json
import threading

_loop: asyncio.AbstractEventLoop | None = None
_subs: set[asyncio.Queue] = set()
_lock = threading.Lock()


def bind_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    with _lock:
        _subs.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _lock:
        _subs.discard(q)


def publish(kind: str, data: dict | None = None) -> None:
    """Safe to call from any thread."""
    msg = json.dumps({"kind": kind, **(data or {})})
    if _loop is None:
        return

    def _put():
        for q in list(_subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass
    try:
        _loop.call_soon_threadsafe(_put)
    except RuntimeError:
        pass
