"""World (WGS84) -> camera pixel projection for DJI Matrice 4E.

The DJI gimbal Euler convention is **not** publicly specified; the working convention is loaded
from configs/projection.yaml, which `scripts/pipeline.py calibrate` writes after brute-forcing
the convention against LRF target bore-sight observations.

Frames used:
    ENU       -- pymap3d's local east-north-up at the camera position
    intermediate -- ENU after a static swap matrix (typically ENU -> NED)
    body      -- drone body after gimbal yaw/pitch/roll (typically x-forward, y-right, z-down)
    image     -- OpenCV camera frame (x-right, y-down, z-into-scene)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation

from .geometry import geodetic_to_enu


@dataclass(frozen=True)
class ProjectionConvention:
    """Resolved rotation convention from configs/projection.yaml.

    `invert_rotation=True` means we apply the rotation's *inverse* (the typical aerospace case:
    yaw/pitch/roll describe how the body is oriented relative to NED, and we need the inverse
    to map NED vectors into the body frame). `False` applies the active rotation directly.
    """

    enu_to_intermediate: np.ndarray  # 3x3
    euler_order: str  # e.g. 'ZYX'
    yaw_sign: int  # +1 or -1
    pitch_sign: int  # +1 or -1
    roll_sign: int  # +1 or -1
    body_to_image: np.ndarray  # 3x3
    invert_rotation: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProjectionConvention:
        return cls(
            enu_to_intermediate=np.array(d["enu_to_intermediate"], dtype=float),
            euler_order=str(d["euler_order"]),
            yaw_sign=int(d["yaw_sign"]),
            pitch_sign=int(d["pitch_sign"]),
            roll_sign=int(d["roll_sign"]),
            body_to_image=np.array(d["body_to_image"], dtype=float),
            invert_rotation=bool(d.get("invert_rotation", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enu_to_intermediate": self.enu_to_intermediate.tolist(),
            "euler_order": self.euler_order,
            "yaw_sign": self.yaw_sign,
            "pitch_sign": self.pitch_sign,
            "roll_sign": self.roll_sign,
            "body_to_image": self.body_to_image.tolist(),
            "invert_rotation": self.invert_rotation,
        }


# Default before calibration. ENU -> NED swap, ZYX intrinsic with DJI pitch sign flipped.
# Calibration script overrides this in configs/projection.yaml.
DEFAULT_CONVENTION = ProjectionConvention(
    enu_to_intermediate=np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]),
    euler_order="ZYX",
    yaw_sign=+1,
    pitch_sign=-1,
    roll_sign=+1,
    body_to_image=np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]),
)


def world_to_image(
    target_lat: float,
    target_lon: float,
    target_alt_m: float,
    camera_lat: float,
    camera_lon: float,
    camera_alt_m: float,
    gimbal_yaw_deg: float,
    gimbal_pitch_deg: float,
    gimbal_roll_deg: float,
    fx_px: float,
    fy_px: float,
    cx_px: float,
    cy_px: float,
    width: int,
    height: int,
    convention: ProjectionConvention = DEFAULT_CONVENTION,
) -> tuple[float | None, float | None, bool, bool]:
    """Project a world point to image pixels.

    Returns (u, v, behind, in_frame). When behind=True, (u, v) is (None, None).
    """
    enu = np.array(
        geodetic_to_enu(
            target_lat, target_lon, target_alt_m, camera_lat, camera_lon, camera_alt_m
        ),
        dtype=float,
    )
    intermediate = convention.enu_to_intermediate @ enu

    rot = Rotation.from_euler(
        convention.euler_order,
        [
            convention.yaw_sign * gimbal_yaw_deg,
            convention.pitch_sign * gimbal_pitch_deg,
            convention.roll_sign * gimbal_roll_deg,
        ],
        degrees=True,
    )
    body = rot.apply(intermediate, inverse=convention.invert_rotation)
    image = convention.body_to_image @ body

    z = image[2]
    if z <= 1e-6:
        return None, None, True, False

    u = fx_px * (image[0] / z) + cx_px
    v = fy_px * (image[1] / z) + cy_px
    in_frame = (0.0 <= u < width) and (0.0 <= v < height)
    return float(u), float(v), False, bool(in_frame)


def project_papi_lights(
    image_row: dict[str, Any],
    papi_config: dict[str, Any],
    camera_config: dict[str, Any],
    convention: ProjectionConvention = DEFAULT_CONVENTION,
) -> dict[int, tuple[float | None, float | None, bool, bool]]:
    """Project all 4 PAPI lights for one image row.

    Returns {light_number: (u, v, behind, in_frame)} for lights 1..4.
    """
    default_alt = float(papi_config["default_alt_wgs84_m"])
    fx = fy = float(camera_config["calibrated_focal_px"])
    cx = float(camera_config["optical_center_x"])
    cy = float(camera_config["optical_center_y"])
    width = int(camera_config["width"])
    height = int(camera_config["height"])

    out: dict[int, tuple[float | None, float | None, bool, bool]] = {}
    for i in range(1, 5):
        light = papi_config[f"light_{i}"]
        out[i] = world_to_image(
            target_lat=float(light["lat"]),
            target_lon=float(light["lon"]),
            target_alt_m=float(light["alt"]) if light.get("alt") is not None else default_alt,
            camera_lat=float(image_row["lat"]),
            camera_lon=float(image_row["lon"]),
            camera_alt_m=float(image_row["alt_ellipsoidal_m"]),
            gimbal_yaw_deg=float(image_row["gimbal_yaw_deg"]),
            gimbal_pitch_deg=float(image_row["gimbal_pitch_deg"]),
            gimbal_roll_deg=float(image_row["gimbal_roll_deg"]),
            fx_px=fx,
            fy_px=fy,
            cx_px=cx,
            cy_px=cy,
            width=width,
            height=height,
            convention=convention,
        )
    return out
