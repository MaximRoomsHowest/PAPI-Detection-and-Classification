"""Per-lamp white/red/transition state derived from elevation-angle geometry.

A PAPI light is white when viewed from above its design set-angle, red when viewed from below,
and visually in transition near the boundary (the lamp has a small angular blend zone). We
mirror that physics: above set+halfwidth = white, below set-halfwidth = red, else transition.
"""

from __future__ import annotations

from typing import Any

from .geometry import elevation_angle_deg

LampState = str  # "white" | "red" | "transition"


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

    states: list[LampState] = []
    min_margin = float("inf")
    for i in range(1, 5):
        light = papi_config[f"light_{i}"]
        elev = elevation_angle_deg(
            camera_lat=float(image_row["lat"]),
            camera_lon=float(image_row["lon"]),
            camera_alt_m=float(image_row["alt_ellipsoidal_m"]),
            target_lat=float(light["lat"]),
            target_lon=float(light["lon"]),
            target_alt_m=_lamp_alt(papi_config, i),
        )
        set_angle = _set_angle(papi_config, i)
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
