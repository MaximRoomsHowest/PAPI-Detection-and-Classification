"""Projection tests: identity, behind-camera, LRF round-trip on a real fixture."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from papi.metadata import extract_image_metadata
from papi.projection import DEFAULT_CONVENTION, ProjectionConvention, world_to_image

REPO_ROOT = Path(__file__).resolve().parents[1]
PAPI_CFG = REPO_ROOT / "configs" / "papi_edny.yaml"
PROJ_CFG = REPO_ROOT / "configs" / "projection.yaml"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _wide_camera_cfg() -> dict:
    return _load_yaml(PAPI_CFG)["cameras"]["wide"]


def _airport_cfg() -> dict:
    return _load_yaml(PAPI_CFG)


def _convention() -> ProjectionConvention:
    if PROJ_CFG.exists():
        return ProjectionConvention.from_dict(_load_yaml(PROJ_CFG)["convention"])
    return DEFAULT_CONVENTION


def test_projection_identity_below_optical_center():
    """A point 10 m forward + 1 m below a horizontal camera should project below center.

    Camera at (47.668, 9.504, 465 m WGS84) facing north (yaw=0), pitch=0, roll=0.
    Target 10 m due north and 1 m below.
    """
    cam = _wide_camera_cfg()
    # We compute the target's lat/lon by displacing the camera 10 m north on the ellipsoid.
    # 10 m / earth_meridional ≈ 0.0000898° per metre of latitude.
    cam_lat, cam_lon, cam_alt = 47.668, 9.504, 465.0
    target_lat = cam_lat + 10 * (1.0 / 111_111.0)
    target_lon = cam_lon
    target_alt = cam_alt - 1.0  # 1 m below the camera

    u, v, behind, in_frame = world_to_image(
        target_lat=target_lat,
        target_lon=target_lon,
        target_alt_m=target_alt,
        camera_lat=cam_lat,
        camera_lon=cam_lon,
        camera_alt_m=cam_alt,
        gimbal_yaw_deg=0.0,
        gimbal_pitch_deg=0.0,
        gimbal_roll_deg=0.0,
        fx_px=float(cam["calibrated_focal_px"]),
        fy_px=float(cam["calibrated_focal_px"]),
        cx_px=float(cam["optical_center_x"]),
        cy_px=float(cam["optical_center_y"]),
        width=int(cam["width"]),
        height=int(cam["height"]),
        convention=DEFAULT_CONVENTION,
    )
    assert not behind, "target ahead and below should not be behind the camera"
    assert u is not None and v is not None
    # u should be approximately the optical center x (target is on the optical axis horizontally)
    assert abs(u - float(cam["optical_center_x"])) < 5.0
    # v should be below the optical center (numerically larger because image y points down)
    assert v > float(cam["optical_center_y"])


def test_projection_behind_camera_returns_behind_true():
    """A point directly behind the camera (180° from gimbal yaw) returns behind=True."""
    cam = _wide_camera_cfg()
    cam_lat, cam_lon, cam_alt = 47.668, 9.504, 465.0
    # camera faces north (yaw=0); target 10 m south = behind
    target_lat = cam_lat - 10 * (1.0 / 111_111.0)
    target_lon = cam_lon
    target_alt = cam_alt

    _, _, behind, in_frame = world_to_image(
        target_lat=target_lat,
        target_lon=target_lon,
        target_alt_m=target_alt,
        camera_lat=cam_lat,
        camera_lon=cam_lon,
        camera_alt_m=cam_alt,
        gimbal_yaw_deg=0.0,
        gimbal_pitch_deg=0.0,
        gimbal_roll_deg=0.0,
        fx_px=float(cam["calibrated_focal_px"]),
        fy_px=float(cam["calibrated_focal_px"]),
        cx_px=float(cam["optical_center_x"]),
        cy_px=float(cam["optical_center_y"]),
        width=int(cam["width"]),
        height=int(cam["height"]),
        convention=DEFAULT_CONVENTION,
    )
    assert behind
    assert not in_frame


def _find_lrf_normal_wide_frame() -> Path | None:
    raw = REPO_ROOT / "data" / "raw"
    if not raw.exists():
        return None
    # Walk a few flights looking for a WideCamera frame with LRFStatus=Normal
    for flight in sorted(raw.iterdir())[:5]:
        if not flight.is_dir():
            continue
        for jpg in sorted(flight.glob("*.JPG"))[:20]:
            meta = extract_image_metadata(jpg)
            if meta.get("camera") == "WideCamera" and meta.get("lrf_status") == "Normal":
                return jpg
    return None


@pytest.mark.skipif(not PROJ_CFG.exists(), reason="run `python scripts/pipeline.py calibrate` first")
def test_lrf_roundtrip_within_200px():
    """Projecting the LRF target lat/lon through the calibrated pipeline must land near image center."""
    jpg = _find_lrf_normal_wide_frame()
    if jpg is None:
        pytest.skip("no LRF-Normal WideCamera frame found under data/raw")

    meta = extract_image_metadata(jpg)
    cam = _wide_camera_cfg()
    conv = _convention()

    u, v, behind, in_frame = world_to_image(
        target_lat=float(meta["lrf_target_lat"]),
        target_lon=float(meta["lrf_target_lon"]),
        target_alt_m=float(meta["lrf_target_abs_alt_m"]) if meta["lrf_target_abs_alt_m"] is not None else 465.0,
        camera_lat=float(meta["lat"]),
        camera_lon=float(meta["lon"]),
        camera_alt_m=float(meta["alt_ellipsoidal_m"]),
        gimbal_yaw_deg=float(meta["gimbal_yaw_deg"]),
        gimbal_pitch_deg=float(meta["gimbal_pitch_deg"]),
        gimbal_roll_deg=float(meta["gimbal_roll_deg"]),
        fx_px=float(cam["calibrated_focal_px"]),
        fy_px=float(cam["calibrated_focal_px"]),
        cx_px=float(cam["optical_center_x"]),
        cy_px=float(cam["optical_center_y"]),
        width=int(cam["width"]),
        height=int(cam["height"]),
        convention=conv,
    )
    assert not behind, f"LRF target reported as behind camera for {jpg.name}"
    assert u is not None and v is not None
    dx = u - float(cam["optical_center_x"])
    dy = v - float(cam["optical_center_y"])
    residual = float(np.hypot(dx, dy))
    assert residual < 200.0, f"LRF residual {residual:.1f}px exceeds 200px for {jpg.name}"
