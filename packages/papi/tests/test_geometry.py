"""Tests for `papi.geometry`.

This module is the angle-math foundation under both the offline
auto-labelling pipeline and the online inference response — every
elevation angle on the Live Demo flows through `elevation_angle_deg`,
and every "which PAPI is this frame looking at?" decision flows
through `resolve_papi_for_frame`. Before these tests it had zero
unit coverage (only the broader projection tests in
``test_projection.py`` touched it indirectly).

Test strategy:

* Identity / degenerate cases first (same point, on the horizon,
  straight up, straight down) — these pin the function shape so a
  refactor that swaps signs gets caught immediately.
* Two known-distance ground-truth cases for ``horizontal_distance_m``
  so a future ellipsoid change isn't silently masked.
* Realistic PAPI geometry sourced from ``configs/papi_edny.yaml`` for
  the dual-runway resolver — the file is also the runtime config, so
  these tests double as "the runtime config still parses" smoke
  coverage.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml
from papi.geometry import (
    elevation_angle_deg,
    geodetic_to_enu,
    horizontal_distance_m,
    resolve_papi_for_frame,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PAPI_CFG = REPO_ROOT / "configs" / "papi_edny.yaml"


# ---------------------------------------------------------------------------
# geodetic_to_enu
# ---------------------------------------------------------------------------


def test_geodetic_to_enu_identity_is_zero_vector():
    """Same observer + target ⇒ zero displacement (no epsilon needed)."""
    e, n, u = geodetic_to_enu(47.5, 9.5, 460.0, 47.5, 9.5, 460.0)
    assert e == pytest.approx(0.0, abs=1e-6)
    assert n == pytest.approx(0.0, abs=1e-6)
    assert u == pytest.approx(0.0, abs=1e-6)


def test_geodetic_to_enu_north_displacement_increases_n_only():
    """Target 10 m due north of observer ⇒ n≈10, e≈0, u≈0."""
    observer_lat, observer_lon, alt = 47.668, 9.504, 465.0
    # ~1 m latitude ≈ 1 / 111_111 degrees.
    target_lat = observer_lat + 10 * (1.0 / 111_111.0)
    e, n, u = geodetic_to_enu(target_lat, observer_lon, alt, observer_lat, observer_lon, alt)
    assert n == pytest.approx(10.0, abs=0.1)
    assert abs(e) < 0.1
    assert abs(u) < 0.1


def test_geodetic_to_enu_up_displacement_increases_u_only():
    """Target 5 m above observer ⇒ u≈5, e≈0, n≈0."""
    observer_lat, observer_lon, alt = 47.668, 9.504, 465.0
    e, n, u = geodetic_to_enu(observer_lat, observer_lon, alt + 5.0, observer_lat, observer_lon, alt)
    assert u == pytest.approx(5.0, abs=1e-3)
    assert abs(e) < 1e-3
    assert abs(n) < 1e-3


# ---------------------------------------------------------------------------
# horizontal_distance_m
# ---------------------------------------------------------------------------


def test_horizontal_distance_m_zero_when_points_coincide():
    assert horizontal_distance_m(47.5, 9.5, 47.5, 9.5) == pytest.approx(0.0, abs=1e-9)


def test_horizontal_distance_m_one_degree_latitude_is_about_111km():
    """One degree of latitude is ~111.2 km on the WGS84 mean sphere.

    We use a generous tolerance because ``horizontal_distance_m`` is a
    great-circle estimate on a sphere of radius 6 371 km — the
    ellipsoidal truth is within ~0.5 % which is what we pin here.
    """
    d = horizontal_distance_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_195.0, rel=0.005)


def test_horizontal_distance_m_papi_24_lamp_1_to_lamp_4_is_about_30m():
    """Pin the geometry against the surveyed coords in the runtime config.

    PAPI 24 light 1 and light 4 are ~30 m apart along the runway-perpendicular
    axis (the cluster spans 4 lamps × ~10 m). If this drifts materially,
    either the survey changed or the haversine formula is broken.
    """
    cfg = yaml.safe_load(PAPI_CFG.read_text(encoding="utf-8"))
    l1 = cfg["runways"]["24"]["papi"]["light_1"]
    l4 = cfg["runways"]["24"]["papi"]["light_4"]
    d = horizontal_distance_m(float(l1["lat"]), float(l1["lon"]), float(l4["lat"]), float(l4["lon"]))
    # The exact spacing depends on the survey; 25-35 m is the credible band.
    assert 25.0 <= d <= 35.0, f"PAPI 24 lamp 1 ↔ lamp 4 is {d:.1f} m, outside the expected 25-35 m band"


def test_horizontal_distance_m_is_symmetric():
    """f(a, b) == f(b, a) — pinning a basic invariant."""
    d_ab = horizontal_distance_m(47.0, 9.0, 47.5, 9.5)
    d_ba = horizontal_distance_m(47.5, 9.5, 47.0, 9.0)
    assert d_ab == pytest.approx(d_ba, abs=1e-9)


# ---------------------------------------------------------------------------
# elevation_angle_deg
# ---------------------------------------------------------------------------


def test_elevation_angle_zero_when_camera_at_same_altitude_far_horizontal():
    """Camera and lamp at the same altitude, 500 m apart ⇒ angle ≈ 0°."""
    cam_lat, cam_lon, alt = 47.668, 9.504, 465.0
    target_lat = cam_lat + 500 * (1.0 / 111_111.0)  # 500 m north
    angle = elevation_angle_deg(
        camera_lat=cam_lat,
        camera_lon=cam_lon,
        camera_alt_m=alt,
        target_lat=target_lat,
        target_lon=cam_lon,
        target_alt_m=alt,
    )
    assert abs(angle) < 0.05  # < 3 arcminutes


def test_elevation_angle_three_degrees_at_glideslope_geometry():
    """Camera 26.2 m above lamp, 500 m horizontal ⇒ 3° elevation (the PAPI design).

    Three degrees is the canonical glideslope, and 26.2 / 500 = tan(3°) within
    rounding. This is the single most important real-world value the function
    must hit.
    """
    cam_lat, cam_lon = 47.668, 9.504
    target_lat = cam_lat + 500 * (1.0 / 111_111.0)
    target_alt = 465.0
    cam_alt = target_alt + 26.2
    angle = elevation_angle_deg(
        camera_lat=cam_lat,
        camera_lon=cam_lon,
        camera_alt_m=cam_alt,
        target_lat=target_lat,
        target_lon=cam_lon,
        target_alt_m=target_alt,
    )
    assert angle == pytest.approx(3.0, abs=0.05)


def test_elevation_angle_negative_when_camera_below_target():
    """Camera 10 m below lamp, 500 m away ⇒ negative angle."""
    cam_lat, cam_lon = 47.668, 9.504
    target_lat = cam_lat + 500 * (1.0 / 111_111.0)
    target_alt = 465.0
    cam_alt = target_alt - 10.0
    angle = elevation_angle_deg(
        camera_lat=cam_lat,
        camera_lon=cam_lon,
        camera_alt_m=cam_alt,
        target_lat=target_lat,
        target_lon=cam_lon,
        target_alt_m=target_alt,
    )
    assert angle < 0
    # tan⁻¹(10 / 500) ≈ 1.146°.
    assert angle == pytest.approx(-1.146, abs=0.05)


def test_elevation_angle_straight_up_returns_ninety():
    """Degenerate case: zero horizontal offset, camera above target ⇒ +90°.

    Pins the special branch (`horiz == 0.0`) in the implementation.
    """
    angle = elevation_angle_deg(
        camera_lat=47.668,
        camera_lon=9.504,
        camera_alt_m=465.0,
        target_lat=47.668,
        target_lon=9.504,
        target_alt_m=455.0,  # 10 m below the camera, no horizontal offset
    )
    assert angle == pytest.approx(90.0, abs=0.01)


def test_elevation_angle_straight_down_returns_minus_ninety():
    """Mirror of the previous test."""
    angle = elevation_angle_deg(
        camera_lat=47.668,
        camera_lon=9.504,
        camera_alt_m=455.0,
        target_lat=47.668,
        target_lon=9.504,
        target_alt_m=465.0,
    )
    assert angle == pytest.approx(-90.0, abs=0.01)


# ---------------------------------------------------------------------------
# resolve_papi_for_frame
# ---------------------------------------------------------------------------


def _airport_cfg() -> dict:
    return yaml.safe_load(PAPI_CFG.read_text(encoding="utf-8"))


def test_resolve_papi_for_frame_picks_rwy_06_from_night_position():
    """An observer near PAPI 06 light 1 ⇒ resolves to runway 06.

    PAPI 06 light 1 is at (lat=47.668810, lon=9.504007). Place the
    "camera" close to it and confirm the resolver picks 06, not 24
    (which is ~1.3 km away on the other end of the runway).
    """
    cfg = _airport_cfg()
    image_row = {"lat": 47.6685, "lon": 9.5040, "alt": 465.0}
    runway, flat = resolve_papi_for_frame(image_row, cfg)
    assert runway == "06"
    assert "light_1" in flat and "light_4" in flat


def test_resolve_papi_for_frame_picks_rwy_24_from_day_position():
    """An observer near PAPI 24 light 1 ⇒ resolves to runway 24."""
    cfg = _airport_cfg()
    image_row = {"lat": 47.6735, "lon": 9.5181, "alt": 465.0}
    runway, flat = resolve_papi_for_frame(image_row, cfg)
    assert runway == "24"
    assert "light_1" in flat


def test_resolve_papi_for_frame_passes_through_airport_level_constants():
    """The returned dict must carry the top-level constants the lamp-state
    / projection code expects, not just the four lights.

    Pinning this contract because it's the silent failure mode — code
    downstream of the resolver KeyErrors at runtime if these keys go
    missing.
    """
    cfg = _airport_cfg()
    image_row = {"lat": 47.6685, "lon": 9.5040, "alt": 465.0}
    _, flat = resolve_papi_for_frame(image_row, cfg)
    assert "faa_default_set_angles_deg" in flat
    assert "transition_half_width_deg" in flat
    assert "default_alt_wgs84_m" in flat
    # Sanity-check values against the runtime config.
    assert flat["faa_default_set_angles_deg"] == [2.50, 2.83, 3.17, 3.50]
    assert flat["transition_half_width_deg"] == 0.10


def test_resolve_papi_for_frame_handles_midpoint_deterministically():
    """A camera exactly between the two PAPIs should still pick one
    deterministically and not crash.

    The dataset never has frames anywhere near this midpoint (the
    drone hovers on the approach end), but the resolver is called by
    the inference path for arbitrary user uploads. A NaN or KeyError
    here would crash the backend on a malicious / malformed upload.
    """
    cfg = _airport_cfg()
    # Midpoint of PAPI 06 light 1 and PAPI 24 light 1.
    image_row = {
        "lat": (47.668810 + 47.673521) / 2,
        "lon": (9.504007 + 9.518154) / 2,
        "alt": 465.0,
    }
    runway, flat = resolve_papi_for_frame(image_row, cfg)
    assert runway in {"06", "24"}
    assert math.isfinite(float(flat["light_1"]["lat"]))
