"""Staff login for hosted mode.

Set STAFF_PASSWORD to turn it on (the booth laptop leaves it unset). Staff log
in once per browser; a signed cookie then unlocks the staff API. Public pages
(home, big screen, Explorer viewing, participant phone pages) need no login.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

from fastapi import Request
from fastapi.responses import JSONResponse

COOKIE = "bdas_staff"

PUBLIC_GET = [re.compile(p) for p in (
    r"^/api/(health|stream|settings|leaderboard|leaderboards|dashboard|profiles)$",
    r"^/api/courses/active$",
    r"^/api/courses/\d+/background$",
    r"^/api/recordings$",
    r"^/api/recordings/\d+(/analysis|/timeseries|/replay)?$",
    r"^/api/runs/\d+/public$",
    r"^/api/p/[\w-]+$",
    r"^/api/qr/station/[\w-]+$",
    r"^/api/auth/me$",
)]
PUBLIC_POST = [re.compile(p) for p in (
    r"^/api/auth/(login|logout)$",
    r"^/api/qr/scan$",
)]


def password() -> str | None:
    return os.environ.get("STAFF_PASSWORD") or None


def required() -> bool:
    return password() is not None


def token() -> str:
    return hmac.new(password().encode(), b"bdas-staff-v1", hashlib.sha256).hexdigest()


def check_password(pw: str) -> bool:
    p = password()
    return p is not None and hmac.compare_digest(pw.encode(), p.encode())


def is_staff(request: Request) -> bool:
    if not required():
        return True
    c = request.cookies.get(COOKIE)
    return bool(c) and hmac.compare_digest(c, token())


def is_public(method: str, path: str) -> bool:
    if method == "OPTIONS" or not path.startswith("/api/"):
        return True
    rules = PUBLIC_GET if method in ("GET", "HEAD") else PUBLIC_POST if method == "POST" else []
    return any(r.match(path) for r in rules)


async def middleware(request: Request, call_next):
    if required() and not is_public(request.method, request.url.path) and not is_staff(request):
        return JSONResponse({"detail": "staff login required"}, status_code=401)
    return await call_next(request)
