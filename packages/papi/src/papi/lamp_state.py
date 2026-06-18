"""Per-lamp white/red/transition state derived from elevation-angle geometry.

A PAPI light is white when viewed from above its design set-angle, red when viewed from below,
and visually in transition near the boundary (the lamp has a small angular blend zone). We
mirror that physics: above set+halfwidth = white, below set-halfwidth = red, else transition.
"""

from __future__ import annotations

import math
from typing import Any

from .geometry import elevation_angle_deg

LampState = str  # "white" | "red" | "transition"

# A standard PAPI unit is exactly four lamps, indexed 1..4 innermost-to-outermost
# (config keys ``light_1``..``light_4``). The single source of truth for the lamp count
# across the backend + workflows; named so iteration bounds read as "for each lamp"
# rather than a bare ``range(1, 5)``.
NUM_PAPI_LAMPS = 4
_NUM_LAMPS = NUM_PAPI_LAMPS  # internal alias (kept for the existing call sites below)

# FAA standard per-lamp set angles for a 3.0deg glideslope (lamp 1..4, lowest..highest). The
# canonical CODE-level default; runway configs may override per-runway via
# ``faa_default_set_angles_deg`` in configs/papi_*.yaml (which currently echo this standard).
FAA_DEFAULT_SET_ANGLES_DEG = (2.50, 2.83, 3.17, 3.50)


def _set_angle(papi_config: dict[str, Any], light_no: int) -> float:
    """Return the set-angle for `light_no` (1..4), falling back to FAA defaults."""
    light = papi_config[f"light_{light_no}"]
    if light.get("set_angle_deg") is not None:
        return float(light["set_angle_deg"])
    faa = papi_config["faa_default_set_angles_deg"]
    return float(faa[light_no - 1])


def _lamp_alt(papi_config: dict[str, Any], light_no: int) -> float:
    light = papi_config[f"light_{light_no}"]
    if light.get("alt") is not None:
        return float(light["alt"])
    return float(papi_config["default_alt_wgs84_m"])


def compute_lamp_state(
    image_row: dict[str, Any], papi_config: dict[str, Any]
) -> tuple[tuple[LampState, LampState, LampState, LampState], float]:
    """Return per-lamp states and the smallest angular margin to any set-angle boundary.

    The margin is useful for uncertainty sampling: frames with small margins are near a
    transition boundary and worth manual verification.
    """
    half_width = float(papi_config["transition_half_width_deg"])

    # A missing/NaN camera position makes every elevation NaN, and the band
    # comparison below would then silently fall through to "transition" for every
    # lamp. Reject it up front so the caller records the frame as unknown rather
    # than a fabricated transition (it already catches ValueError).
    camera_lat = float(image_row["lat"])
    camera_lon = float(image_row["lon"])
    camera_alt_m = float(image_row["alt_ellipsoidal_m"])
    if not all(math.isfinite(v) for v in (camera_lat, camera_lon, camera_alt_m)):
        raise ValueError("non-finite camera position (lat / lon / alt_ellipsoidal_m)")

    states: list[LampState] = []
    min_margin = float("inf")
    for i in range(1, _NUM_LAMPS + 1):
        # A malformed papi-config (missing a ``light_N`` entry, its lat/lon, or a
        # fallback default) would otherwise raise a bare KeyError that escapes the
        # caller's degrade-to-"unknown" handler -- pipeline.py only catches
        # (AssertionError, TypeError, ValueError) -- and crash the whole offline
        # run. Convert it to a clear ValueError so a single bad config row is
        # recorded as unknown, like the non-finite-position guard above.
        try:
            light = papi_config[f"light_{i}"]
            target_lat = float(light["lat"])
            target_lon = float(light["lon"])
            target_alt_m = _lamp_alt(papi_config, i)
            set_angle = _set_angle(papi_config, i)
        except KeyError as exc:
            raise ValueError(f"papi_config missing required key {exc}") from exc
        elev = elevation_angle_deg(
            camera_lat=camera_lat,
            camera_lon=camera_lon,
            camera_alt_m=camera_alt_m,
            target_lat=target_lat,
            target_lon=target_lon,
            target_alt_m=target_alt_m,
        )
        delta = elev - set_angle
        # margin = absolute distance to the nearest transition edge (set ± halfwidth)
        if delta > half_width:
            state = "white"
            margin = delta - half_width
        elif delta < -half_width:
            state = "red"
            margin = (-delta) - half_width
        else:
            state = "transition"
            margin = half_width - abs(delta)
        states.append(state)
        if margin < min_margin:
            min_margin = margin

    return tuple(states), float(min_margin)  # type: ignore[return-value]
