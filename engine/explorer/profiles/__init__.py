"""Demo profiles. Each module defines PROFILE; add a module to add a profile."""
from __future__ import annotations

import importlib
import pkgutil

PROFILES: dict[str, dict] = {}

for _m in pkgutil.iter_modules(__path__):
    mod = importlib.import_module(f"{__name__}.{_m.name}")
    if hasattr(mod, "PROFILE"):
        PROFILES[mod.PROFILE["id"]] = mod.PROFILE


def get_profile(pid: str | None) -> dict:
    return PROFILES.get(pid or "generic", PROFILES["generic"])


def list_profiles() -> list[dict]:
    return [{"id": p["id"], "name": p["name"], "description": p.get("description", "")} for p in PROFILES.values()]
