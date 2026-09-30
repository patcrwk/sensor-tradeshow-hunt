"""Run every Explorer analysis once and cache the result as JSON."""
from __future__ import annotations

import json
import time
from pathlib import Path

from ..io.bundle import Bundle
from .environment import environment
from .frequency import frequency
from .location import gps_track, motion
from .overview import overview
from .profiles import get_profile
from .shock import shock
from .story import build_story


def analyze(b: Bundle, profile_id: str | None = None, annotations: list[dict] | None = None,
            cache: Path | None = None) -> dict:
    t0 = time.time()
    prof = get_profile(profile_id)
    a: dict = {"profile": prof, "overview": overview(b)}
    for key, fn in (("frequency", lambda: frequency(b, prof.get("frequency_role"))),
                    ("shock", lambda: shock(b)),
                    ("environment", lambda: environment(b)),
                    ("motion", lambda: motion(b)),
                    ("gps", lambda: gps_track(b))):
        try:
            a[key] = fn()
        except Exception as ex:
            a[key] = {"available": False, "error": f"{type(ex).__name__}: {ex}"}
    a["story"] = build_story(b, a, prof, annotations)
    a["analysis_seconds"] = round(time.time() - t0, 2)
    if cache:
        cache.write_text(json.dumps(a, default=_json))
    return a


def restory(b: Bundle, a: dict, profile_id: str | None, annotations: list[dict] | None) -> dict:
    prof = get_profile(profile_id)
    a["profile"] = prof
    a["story"] = build_story(b, a, prof, annotations)
    return a


def _json(o):
    try:
        import numpy as np
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    return str(o)
