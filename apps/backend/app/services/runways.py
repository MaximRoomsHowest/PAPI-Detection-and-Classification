"""Backend lookup for PAPI runway geometry.

Loads `configs/papi_edny.yaml` at first call (cached) so the backend
and the offline ML pipeline share one source of truth (audit B-CRIT-3
/ M-CROSS-1). The YAML's `null` altitudes fall back to the airport
default; the YAML's `null` set-angles fall back to FAA defaults
(2.50 / 2.83 / 3.17 / 3.50 deg) at the lamp_state layer, not here.

If the YAML can't be read for any reason, we fall back to a hardcoded
copy of the same values so the backend stays functional in CI / tests
that don't have the repo's `configs/` checked out.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import REPO_ROOT
from app.validation.schemas import RunwayResponse

CONFIG_PATH: Path = REPO_ROOT / "configs" / "papi_edny.yaml"

# Last-resort fallback when configs/papi_edny.yaml is unavailable. Values
# pinned from the YAML at the time of the 2026-05-27 audit. If you change
# the YAML, the runtime path picks it up automatically — these stay only
# for environments where the configs directory is not present.
_FALLBACK_RUNWAYS: dict[str, dict[str, Any]] = {
    "papi_06": {
        "id": "papi_06",
        "label": "PAPI 06",
        "lights": [
            {"point": 1, "longitude": 9.504007, "latitude": 47.668810, "altitude_m": 465.0},
            {"point": 2, "longitude": 9.503948, "latitude": 47.668881, "altitude_m": 465.0},
            {"point": 3, "longitude": 9.503888, "latitude": 47.668951, "altitude_m": 465.0},
            {"point": 4, "longitude": 9.503828, "latitude": 47.669021, "altitude_m": 465.0},
        ],
    },
    "papi_24": {
        "id": "papi_24",
        "label": "PAPI 24",
        "lights": [
            {"point": 1, "longitude": 9.518154, "latitude": 47.673521, "altitude_m": 461.37},
            {"point": 2, "longitude": 9.518214, "latitude": 47.673450, "altitude_m": 461.37},
            {"point": 3, "longitude": 9.518274, "latitude": 47.673380, "altitude_m": 461.37},
            {"point": 4, "longitude": 9.518333, "latitude": 47.673309, "altitude_m": 461.37},
        ],
    },
}


def _load_runways_from_yaml(path: Path) -> dict[str, dict[str, Any]] | None:
    """Parse the airport YAML into the per-runway shape the backend uses.

    Returns None on any IO / parse error so callers can fall back cleanly.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None

    default_alt = float(data.get("default_alt_wgs84_m", 465.0))
    runways_block = data.get("runways") or {}

    out: dict[str, dict[str, Any]] = {}
    for runway_key, runway_data in runways_block.items():
        # IDs in the YAML are bare ("06", "24"); the API surface uses
        # "papi_06" / "papi_24" — preserve the existing endpoint contract.
        api_id = f"papi_{runway_key}"
        lights = []
        papi_block = (runway_data or {}).get("papi") or {}
        for n in range(1, 5):
            light = papi_block.get(f"light_{n}") or {}
            try:
                lights.append(
                    {
                        "point": n,
                        "longitude": float(light["lon"]),
                        "latitude": float(light["lat"]),
                        "altitude_m": float(light["alt"]) if light.get("alt") is not None else default_alt,
                    }
                )
            except (KeyError, TypeError, ValueError):
                # If any one lamp is malformed, skip the whole runway rather
                # than ship half-data — fall back to the hardcoded copy.
                return None
        out[api_id] = {"id": api_id, "label": f"PAPI {runway_key}", "lights": lights}

    return out or None


@lru_cache(maxsize=1)
def _runways() -> dict[str, dict[str, Any]]:
    """Cached runway map. ``lru_cache`` ensures one YAML read per process."""
    loaded = _load_runways_from_yaml(CONFIG_PATH)
    return loaded if loaded is not None else _FALLBACK_RUNWAYS


def list_runways() -> list[RunwayResponse]:
    return [RunwayResponse(**runway) for runway in _runways().values()]


def get_runway(runway_id: str) -> dict[str, Any]:
    try:
        return _runways()[runway_id]
    except KeyError as exc:
        raise ValueError(f"Unknown runway_id: {runway_id}") from exc
