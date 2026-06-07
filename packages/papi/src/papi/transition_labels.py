"""Geometry-seeded 3-class transition labels + candidate mining.

A lamp is seeded as ``transition`` (class 2) only when validated elevation geometry places it
inside its angular blend zone (``|elevation - set_angle| <= transition_half_width_deg``). This
is *not* colour thresholding: colour features are computed for cross-checking and ranking only,
never to overrule geometry into a label. Every seeded box is a *candidate* for human spot-check
(Phase 5), not a final ground truth.

The per-lamp band logic below mirrors ``lamp_state.compute_lamp_state`` exactly (white above
set+halfwidth, red below set-halfwidth, else transition); it is duplicated here only to expose
*per-lamp* elevation/margin (compute_lamp_state collapses to a single min-margin). Keep the two
in sync.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .geometry import elevation_angle_deg, resolve_papi_for_frame

CLASS_RED, CLASS_WHITE, CLASS_TRANSITION = 0, 1, 2
STATE_TO_CLASS = {"red": CLASS_RED, "white": CLASS_WHITE, "transition": CLASS_TRANSITION}


@dataclass(frozen=True)
class LampGeom:
    """Per-lamp geometric verdict for one frame."""

    lamp_id: int
    state: str  # red | white | transition
    elevation_deg: float
    set_angle_deg: float
    delta_deg: float  # elevation - set_angle
    margin_deg: float  # distance to the nearest blend-zone edge (>=0)
    runway: str


@dataclass
class Candidate:
    """One geometry-seeded transition box flagged for human review."""

    source_id: str
    video_id: str
    frame_number: int
    timestamp: str
    track_id: str
    lamp_position: int
    bbox: str  # "cx,cy,w,h" normalized
    previous_state: str
    candidate_state: str
    next_state: str
    red_confidence: str  # detector cross-check (optional, blank unless run)
    white_confidence: str
    transition_score: str  # filled by Phase 4 scoring
    colour_features: str  # JSON dict
    reason_for_flagging: str
    # geometry extras (beyond the brief's columns — useful for QA/scoring)
    elevation_deg: float = 0.0
    set_angle_deg: float = 0.0
    margin_deg: float = 0.0
    runway: str = ""
    camera: str = ""
    assignment_method: str = ""
    quality_flags: str = ""

    @staticmethod
    def fieldnames() -> list[str]:
        return [
            "source_id", "video_id", "frame_number", "timestamp", "track_id", "lamp_position",
            "bbox", "previous_state", "candidate_state", "next_state", "red_confidence",
            "white_confidence", "transition_score", "colour_features", "reason_for_flagging",
            "elevation_deg", "set_angle_deg", "margin_deg", "runway", "camera",
            "assignment_method", "quality_flags",
        ]

    def as_row(self) -> dict[str, str]:
        return {
            "source_id": self.source_id, "video_id": self.video_id,
            "frame_number": str(self.frame_number), "timestamp": self.timestamp,
            "track_id": self.track_id, "lamp_position": str(self.lamp_position),
            "bbox": self.bbox, "previous_state": self.previous_state,
            "candidate_state": self.candidate_state, "next_state": self.next_state,
            "red_confidence": self.red_confidence, "white_confidence": self.white_confidence,
            "transition_score": self.transition_score, "colour_features": self.colour_features,
            "reason_for_flagging": self.reason_for_flagging,
            "elevation_deg": f"{self.elevation_deg:.4f}", "set_angle_deg": f"{self.set_angle_deg:.4f}",
            "margin_deg": f"{self.margin_deg:.4f}", "runway": self.runway, "camera": self.camera,
            "assignment_method": self.assignment_method, "quality_flags": self.quality_flags,
        }


def lamp_geom_states(metadata_row: dict[str, Any], airport_config: dict[str, Any]) -> dict[int, LampGeom]:
    """Per-lamp geometric state for one frame, or {} if the camera pose is non-finite.

    Mirrors lamp_state.compute_lamp_state's band logic but keeps per-lamp elevation/margin.
    """
    try:
        cam_lat = float(metadata_row["lat"])
        cam_lon = float(metadata_row["lon"])
        cam_alt = float(metadata_row["alt_ellipsoidal_m"])
    except (KeyError, ValueError, TypeError):
        return {}
    if not all(math.isfinite(v) for v in (cam_lat, cam_lon, cam_alt)):
        return {}

    try:
        runway, papi = resolve_papi_for_frame(metadata_row, airport_config)
    except (KeyError, ValueError, TypeError):
        return {}
    half = float(papi["transition_half_width_deg"])
    faa = papi["faa_default_set_angles_deg"]

    out: dict[int, LampGeom] = {}
    for i in range(1, 5):
        light = papi[f"light_{i}"]
        set_angle = light.get("set_angle_deg")
        set_angle = float(set_angle) if set_angle is not None else float(faa[i - 1])
        alt = light.get("alt")
        target_alt = float(alt) if alt is not None else float(papi["default_alt_wgs84_m"])
        elev = elevation_angle_deg(
            camera_lat=cam_lat, camera_lon=cam_lon, camera_alt_m=cam_alt,
            target_lat=float(light["lat"]), target_lon=float(light["lon"]), target_alt_m=target_alt,
        )
        delta = elev - set_angle
        if delta > half:
            state, margin = "white", delta - half
        elif delta < -half:
            state, margin = "red", (-delta) - half
        else:
            state, margin = "transition", half - abs(delta)
        out[i] = LampGeom(i, state, elev, set_angle, delta, margin, runway)
    return out


def colour_features(image_bgr: Any, bbox_norm: tuple[float, float, float, float]) -> dict[str, float]:
    """HSV/Lab colour summary of the inner region of a normalized bbox.

    Inner-60% crop avoids dark halo/edge bleed. Returns ratios + central tendencies; never used
    to set a label, only to score plausibility (orange/amber blur vs a genuine blend).
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
    n = float(hue.size)
    # OpenCV hue is [0,180]. Red wraps both ends; orange/amber ~ 11..25; yellow ~ 26..35.
    red_m = (((hue <= 10) | (hue >= 160)) & (sat > 60) & (val > 60))
    orange_m = ((hue >= 11) & (hue <= 25) & (sat > 50) & (val > 60))
    yellow_m = ((hue >= 26) & (hue <= 35) & (sat > 50) & (val > 60))
    white_m = ((sat < 45) & (val > 170))
    return {
        "n_px": n,
        "red_ratio": float(red_m.mean()),
        "orange_amber_ratio": float(orange_m.mean()),
        "yellow_ratio": float(yellow_m.mean()),
        "white_ratio": float(white_m.mean()),
        "sat_mean": float(sat.mean()), "val_mean": float(val.mean()),
        "hue_median": float(np.median(hue)),
        "lab_a_mean": float(lab[..., 1].astype("float32").mean()),  # >128 = reddish
        "lab_b_mean": float(lab[..., 2].astype("float32").mean()),  # >128 = yellowish
    }


def track_state_sequences(track_rows: list[dict[str, str]]) -> dict[str, list[tuple[int, str]]]:
    """track_id -> ordered [(frame_index, geom_or_label_state)] for prev/next lookup."""
    seqs: dict[str, list[tuple[int, str]]] = {}
    for row in track_rows:
        seqs.setdefault(row["track_id"], []).append((int(row["frame_index"]), row["state"]))
    for tid in seqs:
        seqs[tid].sort(key=lambda t: t[0])
    return seqs


def neighbour_states(seq: list[tuple[int, str]], frame_index: int) -> tuple[str, str]:
    """(previous_state, next_state) around frame_index within a track's ordered sequence."""
    prev_state = next_state = ""
    for idx, (f, _s) in enumerate(seq):
        if f == frame_index:
            if idx > 0:
                prev_state = seq[idx - 1][1]
            if idx + 1 < len(seq):
                next_state = seq[idx + 1][1]
            break
    return prev_state, next_state
