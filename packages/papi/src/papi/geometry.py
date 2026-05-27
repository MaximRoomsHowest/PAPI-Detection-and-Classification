"""Thin wrappers around pymap3d so the rest of the package depends on a narrow surface.

For ENU offsets ≤ 1.5 km (our entire stand-off range), pymap3d's geodetic2enu / enu2geodetic
on the WGS84 ellipsoid is precise enough — no pyproj needed.

Also exposes `resolve_papi_for_frame`, which picks the nearer PAPI runway per-frame — the EDNY
dataset captures BOTH runway 06 (night flights) and runway 24 (day2 flights) installations.
"""

from __future__ import annotations

import math
from typing import Any

import pymap3d as pm


def geodetic_to_enu(
    target_lat: float,
    target_lon: float,
    target_alt_m: float,
    observer_lat: float,
    observer_lon: float,
    observer_alt_m: float,
) -> tuple[float, float, float]:
    """Return (e, n, u) in metres from observer to target on WGS84 ellipsoid."""
    e, n, u = pm.geodetic2enu(
        target_lat, target_lon, target_alt_m, observer_lat, observer_lon, observer_alt_m
    )
    return float(e), float(n), float(u)


def horizontal_distance_m(
    lat_a: float, lon_a: float, lat_b: float, lon_b: float
) -> float:
    """Great-circle distance ignoring altitude. Good to <0.5 m at <10 km separations."""
    r = 6_371_000.0
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    dphi = math.radians(lat_b - lat_a)
    dlmb = math.radians(lon_b - lon_a)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_papi_for_frame(
    image_row: dict[str, Any], airport_config: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Pick the nearer PAPI runway for `image_row` and return a flat papi-config dict.

    The returned dict has keys `light_1`..`light_4` plus the top-level constants the lamp-state
    and projection modules need (`faa_default_set_angles_deg`, `transition_half_width_deg`,
    `default_alt_wgs84_m`). Compatible with `compute_lamp_state` and `project_papi_lights`.
    """
    cam_lat = float(image_row["lat"])
    cam_lon = float(image_row["lon"])
    best_runway: str | None = None
    best_dist = float("inf")
    for runway, rcfg in airport_config["runways"].items():
        l1 = rcfg["papi"]["light_1"]
        d = horizontal_distance_m(cam_lat, cam_lon, float(l1["lat"]), float(l1["lon"]))
        if d < best_dist:
            best_dist = d
            best_runway = str(runway)
    assert best_runway is not None
    flat = dict(airport_config["runways"][best_runway]["papi"])
    flat["faa_default_set_angles_deg"] = airport_config["faa_default_set_angles_deg"]
    flat["transition_half_width_deg"] = airport_config["transition_half_width_deg"]
    flat["default_alt_wgs84_m"] = airport_config["default_alt_wgs84_m"]
    return best_runway, flat


def elevation_angle_deg(
    camera_lat: float,
    camera_lon: float,
    camera_alt_m: float,
    target_lat: float,
    target_lon: float,
    target_alt_m: float,
) -> float:
    """Elevation angle (deg) of the *camera* as observed from the *target* on the ground.

    Used for PAPI lamp-state determination: each PAPI light has a design set-angle; the camera's
    elevation as seen from the light must be compared against that.
    """
    e, n, u = geodetic_to_enu(
        target_lat, target_lon, target_alt_m, camera_lat, camera_lon, camera_alt_m
    )
    horiz = math.hypot(e, n)
    # u (here) = target_alt - camera_alt; we want camera_alt - target_alt:
    alt_above_light = -u
    if horiz == 0.0:
        return 90.0 if alt_above_light >= 0 else -90.0
    return math.degrees(math.atan2(alt_above_light, horiz))
