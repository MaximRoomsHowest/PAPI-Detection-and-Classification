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

import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.config import REPO_ROOT, get_settings
from app.validation.schemas import RunwayCreate, RunwayResponse

CONFIG_PATH: Path = REPO_ROOT / "configs" / "papi_edny.yaml"

# Last-resort fallback when configs/papi_edny.yaml is unavailable. Values
# mirror the YAML: both built-ins use 461.37 m. For papi_06 this is the
# data_analysis-branch lamp reference, not the rejected 464.988 m minimum
# client-drone-MRK altitude floor proxy. If you change the YAML, the runtime path
# picks it up automatically — these stay only for environments where configs/ is
# missing.
_FALLBACK_RUNWAYS: dict[str, dict[str, Any]] = {
    "papi_06": {
        "id": "papi_06",
        "label": "PAPI 06",
        "airport": "EDNY",
        "designation": "06",
        "source": "config",
        "lights": [
            {"point": 1, "longitude": 9.504007, "latitude": 47.668810, "altitude_m": 461.37},
            {"point": 2, "longitude": 9.503948, "latitude": 47.668881, "altitude_m": 461.37},
            {"point": 3, "longitude": 9.503888, "latitude": 47.668951, "altitude_m": 461.37},
            {"point": 4, "longitude": 9.503828, "latitude": 47.669021, "altitude_m": 461.37},
        ],
    },
    "papi_24": {
        "id": "papi_24",
        "label": "PAPI 24",
        "airport": "EDNY",
        "designation": "24",
        "source": "config",
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
    airport = data.get("airport")
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
        out[api_id] = {
            "id": api_id,
            "label": f"PAPI {runway_key}",
            "airport": str(airport) if airport is not None else None,
            "designation": str(runway_key),
            "source": "config",
            "lights": lights,
        }

    return out or None


@lru_cache(maxsize=1)
def _runways() -> dict[str, dict[str, Any]]:
    """Cached built-in runway map (YAML or fallback). One read per process."""
    loaded = _load_runways_from_yaml(CONFIG_PATH)
    return loaded if loaded is not None else _FALLBACK_RUNWAYS


# --- Runtime custom runways -------------------------------------------------
# User-registered runways (POST /api/runways) persist to a JSON sidecar under the
# backend storage dir so they survive a restart and are usable by the analyze
# endpoints (validate_runway_id -> get_runway) and the ENU angle solver, exactly
# like the built-in surveyed runways. Built-in ids are reserved and never shadowed.

# Re-entrant so add_runway/delete_runway can call the self-locking _load_custom
# while already holding the lock (double-checked-locking, like the model load).
_custom_lock = threading.RLock()
_custom_cache: dict[str, dict[str, Any]] | None = None


def _custom_path() -> Path:
    return get_settings().storage_dir / "custom_runways.json"


def _normalise_custom_store(raw: Any) -> dict[str, dict[str, Any]]:
    """Validate the persisted custom-runway sidecar before trusting it."""
    if not isinstance(raw, dict):
        return {}

    store: dict[str, dict[str, Any]] = {}
    for runway_key, runway in raw.items():
        if not isinstance(runway_key, str) or not runway_key.startswith("custom_"):
            continue
        if not isinstance(runway, dict):
            continue

        candidate = {**runway, "id": runway_key, "source": "custom"}
        try:
            validated = RunwayCreate(
                id=runway_key,
                label=candidate.get("label"),
                airport=candidate.get("airport"),
                designation=candidate.get("designation"),
                lights=candidate.get("lights"),
            )
        except (TypeError, ValidationError, ValueError):
            continue

        store[runway_key] = RunwayResponse(
            id=runway_key,
            label=validated.label.strip(),
            airport=(validated.airport or "").strip() or None,
            designation=(validated.designation or "").strip() or None,
            source="custom",
            lights=[
                {
                    "point": light.point,
                    "latitude": light.latitude,
                    "longitude": light.longitude,
                    "altitude_m": light.altitude_m,
                }
                for light in sorted(validated.lights, key=lambda lamp: lamp.point)
            ],
        ).model_dump()
    return store


def _load_custom() -> dict[str, dict[str, Any]]:
    # Self-locking: get_runway()/list_runways() reach here from the analyze
    # threadpool with no lock of their own, so guard the lazy cache init against a
    # concurrent add/delete (which would otherwise read a half-replaced dict).
    global _custom_cache
    with _custom_lock:
        if _custom_cache is None:
            try:
                raw = json.loads(_custom_path().read_text(encoding="utf-8"))
                _custom_cache = _normalise_custom_store(raw)
            except (OSError, json.JSONDecodeError):
                _custom_cache = {}
        return _custom_cache


def _persist_custom(store: dict[str, dict[str, Any]]) -> None:
    # Atomic write: serialise to a temp sibling then replace, so a crash mid-write
    # can't truncate custom_runways.json — a truncated file silently resets to {}
    # on the next load and would lose every registered runway.
    path = _custom_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, indent=2), encoding="utf-8")
    tmp.replace(path)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return slug or "runway"


def _all_runways() -> dict[str, dict[str, Any]]:
    # Built-ins first; a custom id can never shadow a built-in (add_runway rejects
    # reserved ids), so the merge order is purely defensive.
    return {**_runways(), **_load_custom()}


def list_runways() -> list[RunwayResponse]:
    return [RunwayResponse(**runway) for runway in _all_runways().values()]


def get_runway(runway_id: str) -> dict[str, Any]:
    try:
        return _all_runways()[runway_id]
    except KeyError as exc:
        raise ValueError(f"Unknown runway_id: {runway_id}") from exc


# Cap on stored custom runways. The store is unauthenticated by default and is
# rewritten in full on every registration (O(n) JSON dump), so an unbounded create
# loop is a slow-growth DoS; 200 is far above any realistic demo need (audit).
MAX_CUSTOM_RUNWAYS = 200


def add_runway(payload: RunwayCreate) -> dict[str, Any]:
    """Register a runtime runway from a validated ``RunwayCreate`` and persist it.

    Returns the stored, RunwayResponse-shaped dict. Raises ``ValueError`` if the
    derived id collides with a built-in or an existing custom runway.
    """
    global _custom_cache
    with _custom_lock:
        # Mutate a COPY and only swap the live cache in after the disk write
        # succeeds, so a failed _persist_custom (e.g. disk full) can't leave the
        # in-memory cache claiming a runway that was never saved. The copy also
        # gives concurrent readers a stable snapshot instead of a half-mutated dict.
        store = dict(_load_custom())
        raw_id = (payload.id or "").strip() or _slugify(payload.designation or payload.label)
        runway_id = _slugify(raw_id)
        # Namespace every custom runway so it can never collide with papi_06 / papi_24.
        if not runway_id.startswith("custom_"):
            runway_id = f"custom_{runway_id}"
        if runway_id in _runways():
            raise ValueError(f"Runway id '{runway_id}' is reserved by a built-in runway.")
        if runway_id in store:
            raise ValueError(f"Runway '{runway_id}' already exists.")
        if len(store) >= MAX_CUSTOM_RUNWAYS:
            raise ValueError(
                f"Custom-runway limit reached ({MAX_CUSTOM_RUNWAYS}). "
                "Delete an existing custom runway before adding another."
            )
        runway = {
            "id": runway_id,
            "label": payload.label.strip(),
            "airport": (payload.airport or "").strip() or None,
            "designation": (payload.designation or "").strip() or None,
            "source": "custom",
            "lights": [
                {
                    "point": light.point,
                    "latitude": light.latitude,
                    "longitude": light.longitude,
                    "altitude_m": light.altitude_m,
                }
                for light in sorted(payload.lights, key=lambda lamp: lamp.point)
            ],
        }
        store[runway_id] = runway
        _persist_custom(store)
        _custom_cache = store
        return runway


def delete_runway(runway_id: str) -> None:
    """Remove a custom runway. Raises ``ValueError`` for a built-in id and
    ``KeyError`` for an unknown id."""
    global _custom_cache
    with _custom_lock:
        if runway_id in _runways():
            raise ValueError("Built-in runways cannot be deleted.")
        # Mutate a COPY; only swap the live cache in after the disk write succeeds, so
        # a failed _persist_custom can't drop a runway from memory that is still on disk.
        store = dict(_load_custom())
        if runway_id not in store:
            raise KeyError(runway_id)
        del store[runway_id]
        _persist_custom(store)
        _custom_cache = store
