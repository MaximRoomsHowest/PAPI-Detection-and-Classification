"""JSON telemetry parser.

Accepts a single ``{lat,lon,alt}`` object, a bare array of them, or a container
object keyed by ``samples`` / ``track`` / ``points`` / ``telemetry`` / ``frames``.
Named ``json_parser`` (not ``json``) so it does not shadow the stdlib :mod:`json`.
"""

from __future__ import annotations

import json
import logging

from app.services.telemetry.sample import (
    MAX_TELEMETRY_SAMPLES,
    DroneSample,
    _capped_indices,
    _coerce_float,
    _coerce_frame_index,
    _make_sample,
)

logger = logging.getLogger("app.services.telemetry")

_JSON_LAT_KEYS = ("latitude", "lat", "drone_latitude")
_JSON_LON_KEYS = ("longitude", "lon", "lng", "long", "drone_longitude")
_JSON_ALT_KEYS = (
    "altitude_m",
    "altitude",
    "abs_alt",
    "absolute_altitude",
    "alt_ellipsoidal_m",
    "drone_altitude_m",
    "alt",
)
_JSON_FRAME_KEYS = ("frame_index", "frame", "index")
_JSON_TIME_KEYS = ("time_s", "time", "timestamp", "t")


def _pick(entry: dict, keys: tuple[str, ...]) -> object | None:
    lowered = {str(k).lower(): v for k, v in entry.items()}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _parse_json(text: str) -> list[DroneSample]:
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError, RecursionError):
        # RecursionError (deeply-nested array/object) subclasses RuntimeError, not
        # ValueError, so without it here the exception escapes as an unhandled HTTP 500
        # with a stack trace on the unauthenticated analyze path (audit blocker).
        return []

    if isinstance(data, dict):
        for container_key in ("samples", "track", "points", "telemetry", "frames"):
            if isinstance(data.get(container_key), list):
                entries = data[container_key]
                break
        else:
            entries = [data]
    elif isinstance(data, list):
        entries = data
    else:
        return []

    # Cap the materialized list up front (entries is always a list here) so a
    # pathological file can't allocate millions of samples before the post-parse
    # downsample runs (audit #14). Logged so a silently-thinned track is diagnosable.
    total = len(entries)
    if total > MAX_TELEMETRY_SAMPLES:
        logger.warning(
            "Telemetry track downsampled from %d to %d samples (cap).",
            total,
            MAX_TELEMETRY_SAMPLES,
        )
    samples: list[DroneSample] = []
    for order in _capped_indices(total):
        entry = entries[order]
        if not isinstance(entry, dict):
            continue
        lat = _coerce_float(_pick(entry, _JSON_LAT_KEYS))
        lon = _coerce_float(_pick(entry, _JSON_LON_KEYS))
        alt = _coerce_float(_pick(entry, _JSON_ALT_KEYS))
        frame_raw = _pick(entry, _JSON_FRAME_KEYS)
        if frame_raw is None:
            frame_index = order
        else:
            frame_index = _coerce_frame_index(frame_raw)
            if frame_index is None:
                continue
        time_s = _coerce_float(_pick(entry, _JSON_TIME_KEYS))
        sample = _make_sample(lat, lon, alt, frame_index=frame_index, time_s=time_s)
        if sample is not None:
            samples.append(sample)
    return samples
