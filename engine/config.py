"""Loads engine/config.yaml. All thresholds come from here."""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parent
CONFIG_PATH = Path(os.environ.get("ENGINE_CONFIG", ENGINE_DIR / "config.yaml"))


class Cfg(dict):
    """dict with attribute access, recursive."""

    def __getattr__(self, k: str) -> Any:
        try:
            v = self[k]
        except KeyError as e:
            raise AttributeError(k) from e
        return Cfg(v) if isinstance(v, dict) and not isinstance(v, Cfg) else v


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def get_config(overrides: dict | None = None) -> Cfg:
    """Return config, optionally deep-merged with per-course overrides."""
    base = copy.deepcopy(_load())
    if overrides:
        _merge(base, overrides)
    return Cfg(base)


def _merge(dst: dict, src: dict) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def data_dir() -> Path:
    p = Path(os.environ.get("DATA_DIR", get_config().paths.data_dir))
    if not p.is_absolute():
        p = REPO_ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p
