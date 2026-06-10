"""Flip-anchored 3-class transition labels + candidate mining.

METHODOLOGY NOTE (established 2026-06-07 from data, not assumption). A first attempt seeded
``transition`` from the geometric blend zone (|elevation - set_angle| <= half_width). It was
abandoned after diagnostics showed the seeded frames are *disjoint* from where lamps actually
change colour: a tracked lamp's red<->white flip occurs at an elevation matching a DIFFERENT
config light than its ``physical_lamp_id`` -- i.e. the lamp-order<->set-angle binding in
configs/papi_edny*.yaml does not match the data (the unresolved "Punktnummer" binding flagged in
BigBrain). Geometry as configured cannot place the transition.

The authoritative source of genuine transitions is ``transitions.csv``, derived from the
human-corrected red/white labels. We therefore *anchor* transition labels to those real flips:
a short window of frames around each red<->white change, where colour diagnostics confirm the
lamp is visibly intermediate (red_ratio falls / white_ratio rises / saturation drops). Geometry
is kept only to derive each lamp's EMPIRICAL set-angle (median approach-elevation at its flips)
for reporting + angle-binding, and to flag flips whose elevation is discontinuous (bad telemetry).

This satisfies the brief's valid-transition criteria ("temporal evidence from adjacent frames
supports the change"; "short unstable colour phase between two stable states") and avoids the
invalid case of labeling a solid red/white "graze" as transition.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

from .geometry import elevation_angle_deg, resolve_papi_for_frame

CLASS_RED, CLASS_WHITE, CLASS_TRANSITION = 0, 1, 2
ELEV_DISCONTINUITY_DEG = 0.5  # a >0.5deg jump between consecutive frames = suspect telemetry


@dataclass(frozen=True)
class Flip:
    """One authoritative red<->white change for a tracked lamp (from transitions.csv)."""

    track_id: str
    lamp_position: str
    from_frame: int
    to_frame: int
    from_state: str
    to_state: str
    transition_type: str


def approach_elevation_deg(metadata_row: dict[str, Any], airport_config: dict[str, Any]) -> tuple[str, float]:
    """Single approach elevation (deg) to the PAPI centroid, or ('', nan) if pose is unusable.

    All four lamps are angularly co-located from drone stand-off (~0.002deg apart), so one
    approach elevation governs every lamp; the per-lamp set-angle is the threshold it crosses.
    """
    try:
        cam_lat = float(metadata_row["lat"])
        cam_lon = float(metadata_row["lon"])
        cam_alt = float(metadata_row["alt_ellipsoidal_m"])
    except (KeyError, ValueError, TypeError):
        return "", math.nan
    if not all(math.isfinite(v) for v in (cam_lat, cam_lon, cam_alt)):
        return "", math.nan
    try:
        runway, papi = resolve_papi_for_frame(metadata_row, airport_config)
        lats = [float(papi[f"light_{i}"]["lat"]) for i in range(1, 5)]
        lons = [float(papi[f"light_{i}"]["lon"]) for i in range(1, 5)]
        alts = [float(papi[f"light_{i}"].get("alt") or papi["default_alt_wgs84_m"]) for i in range(1, 5)]
    except (KeyError, ValueError, TypeError):
        return "", math.nan
    elev = elevation_angle_deg(
        camera_lat=cam_lat, camera_lon=cam_lon, camera_alt_m=cam_alt,
        target_lat=sum(lats) / 4, target_lon=sum(lons) / 4, target_alt_m=sum(alts) / 4,
    )
    return runway, elev


def parse_flips(transition_rows: list[dict[str, str]]) -> list[Flip]:
    flips: list[Flip] = []
    for row in transition_rows:
        flips.append(
            Flip(
                track_id=row["track_id"], lamp_position=row.get("physical_lamp_id", ""),
                from_frame=int(row["from_frame_index"]), to_frame=int(row["to_frame_index"]),
                from_state=row["from_state"], to_state=row["to_state"],
                transition_type=row["transition_type"],
            )
        )
    return flips


def window_frames(flip: Flip, half_window: int, observed: set[int]) -> list[int]:
    """Observed frames within +/-half_window of the flip boundary (from_frame..to_frame)."""
    lo, hi = flip.from_frame - half_window + 1, flip.to_frame + half_window - 1
    return sorted(f for f in observed if lo <= f <= hi)


def empirical_set_angle(elevations: list[float]) -> float | None:
    """Median approach elevation at a lamp's flips = its data-derived set-angle."""
    clean = [e for e in elevations if e is not None and math.isfinite(e)]
    return statistics.median(clean) if clean else None


def colour_features(image_bgr: Any, bbox_norm: tuple[float, float, float, float]) -> dict[str, float]:
    """HSV/Lab colour summary of the inner region of a normalized bbox.

    Inner-60% crop avoids dark halo/edge bleed. Used to rank/confirm a flip-anchored candidate
    (red_ratio down + white_ratio up + saturation down across the window = a genuine blend);
    never used on its own to create a label.
    """
    import cv2
    import numpy as np

    h_img, w_img = image_bgr.shape[:2]
    cx, cy, bw, bh = bbox_norm
    half_w, half_h = bw * 0.30, bh * 0.30  # inner 60%
    x1 = max(0, int((cx - half_w) * w_img))
    x2 = min(w_img, int((cx + half_w) * w_img) + 1)
    y1 = max(0, int((cy - half_h) * h_img))
    y2 = min(h_img, int((cy + half_h) * h_img) + 1)
    crop = image_bgr[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] * crop.shape[1] < 4:
        return {"n_px": 0}

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    hue, sat, val = hsv[..., 0].astype("float32"), hsv[..., 1].astype("float32"), hsv[..., 2].astype("float32")
    # OpenCV hue is [0,180]. Red wraps both ends; orange/amber ~ 11..25; yellow ~ 26..35.
    red_m = (((hue <= 10) | (hue >= 160)) & (sat > 60) & (val > 60))
    orange_m = ((hue >= 11) & (hue <= 25) & (sat > 50) & (val > 60))
    yellow_m = ((hue >= 26) & (hue <= 35) & (sat > 50) & (val > 60))
    white_m = ((sat < 45) & (val > 170))
    return {
        "n_px": float(hue.size),
        "red_ratio": float(red_m.mean()),
        "orange_amber_ratio": float(orange_m.mean()),
        "yellow_ratio": float(yellow_m.mean()),
        "white_ratio": float(white_m.mean()),
        "sat_mean": float(sat.mean()), "val_mean": float(val.mean()),
        "hue_median": float(np.median(hue)),
        "lab_a_mean": float(lab[..., 1].astype("float32").mean()),  # >128 = reddish
        "lab_b_mean": float(lab[..., 2].astype("float32").mean()),  # >128 = yellowish
    }


@dataclass
class Candidate:
    """One flip-anchored transition box flagged for human review."""

    source_id: str
    video_id: str
    frame_number: int
    timestamp: str
    track_id: str
    lamp_position: str
    bbox: str
    previous_state: str  # stable colour before the flip
    candidate_state: str  # "transition"
    next_state: str  # stable colour after the flip
    transition_type: str  # red_to_white | white_to_red
    flip_frame: int
    frame_offset: int  # signed frames from the flip boundary
    approach_elevation_deg: float
    empirical_set_angle_deg: str
    runway: str
    camera: str
    colour_features: str
    transition_score: str  # filled by Phase 4
    reason_for_flagging: str
    quality_flags: str

    @staticmethod
    def fieldnames() -> list[str]:
        return [
            "candidate_id", "source_id", "video_id", "frame_number", "timestamp", "track_id",
            "lamp_position", "bbox", "previous_state", "candidate_state", "next_state",
            "transition_type", "flip_frame", "frame_offset", "approach_elevation_deg",
            "empirical_set_angle_deg", "runway", "camera", "colour_features", "transition_score",
            "reason_for_flagging", "quality_flags",
        ]

    def as_row(self, candidate_id: str) -> dict[str, str]:
        return {
            "candidate_id": candidate_id, "source_id": self.source_id, "video_id": self.video_id,
            "frame_number": str(self.frame_number), "timestamp": self.timestamp,
            "track_id": self.track_id, "lamp_position": self.lamp_position, "bbox": self.bbox,
            "previous_state": self.previous_state, "candidate_state": self.candidate_state,
            "next_state": self.next_state, "transition_type": self.transition_type,
            "flip_frame": str(self.flip_frame), "frame_offset": str(self.frame_offset),
            # Empty string when telemetry is missing — a plausible-looking "0.0000"
            # made missing-elevation rows indistinguishable from a genuine 0° (LS-9).
            "approach_elevation_deg": (
                f"{self.approach_elevation_deg:.4f}"
                if math.isfinite(self.approach_elevation_deg)
                else ""
            ),
            "empirical_set_angle_deg": self.empirical_set_angle_deg, "runway": self.runway,
            "camera": self.camera, "colour_features": self.colour_features,
            "transition_score": self.transition_score, "reason_for_flagging": self.reason_for_flagging,
            "quality_flags": self.quality_flags,
        }
