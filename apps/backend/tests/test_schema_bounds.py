"""Pydantic validation-bound coverage for app.validation.schemas.

These models guard the response contract and the crop/overlay math. The
bounds are documented in the model docstrings; this file pins them so a
relaxed/removed validator is a failing test rather than a silent regression.

Pinned here:
  * BoundingBox rejects inverted coordinates (x2<x1, y2<y1) but allows a
    zero-area box (a single-pixel lamp is legitimate).
  * AnalysisPayload.confidence is constrained to [0, 1] (it is a probability).
  * Detection.confidence is likewise constrained to [0, 1].
  * AnglePerLight.distance_m is non-negative (it is a hypot, never negative).
"""

from __future__ import annotations

import pytest
from app.validation.schemas import (
    AnalysisPayload,
    AnglePerLight,
    AngleResult,
    BoundingBox,
    Detection,
    RunwayCreate,
)
from pydantic import ValidationError

# --- BoundingBox ----------------------------------------------------------


def test_bounding_box_rejects_x2_less_than_x1():
    with pytest.raises(ValidationError, match="x2 must be >= x1"):
        BoundingBox(x1=10, y1=10, x2=5, y2=20)


def test_bounding_box_rejects_y2_less_than_y1():
    with pytest.raises(ValidationError, match="y2 must be >= y1"):
        BoundingBox(x1=10, y1=10, x2=20, y2=5)


def test_bounding_box_allows_zero_area_box():
    """A single-pixel box (x2==x1 and y2==y1) is valid per the docstring."""
    box = BoundingBox(x1=5, y1=5, x2=5, y2=5)
    assert (box.x1, box.y1, box.x2, box.y2) == (5, 5, 5, 5)


def test_bounding_box_allows_well_formed_box():
    box = BoundingBox(x1=1, y1=2, x2=30, y2=40)
    assert box.x2 >= box.x1 and box.y2 >= box.y1


# --- confidence in [0, 1] -------------------------------------------------


def _payload(confidence: float) -> AnalysisPayload:
    return AnalysisPayload(
        media_type="image",
        original_filename="frame.jpg",
        runway_id="papi_24",
        global_state="unknown",
        lamps=[],
        confidence=confidence,
        frame_count=1,
        processing_ms=1,
        angle=AngleResult(angle_available=False, angle_note="no metadata"),
    )


def test_analysis_payload_confidence_above_one_rejected():
    with pytest.raises(ValidationError):
        _payload(1.5)


def test_analysis_payload_confidence_below_zero_rejected():
    with pytest.raises(ValidationError):
        _payload(-0.01)


def test_analysis_payload_confidence_boundaries_accepted():
    assert _payload(0.0).confidence == 0.0
    assert _payload(1.0).confidence == 1.0


def test_detection_confidence_out_of_range_rejected():
    bbox = BoundingBox(x1=0, y1=0, x2=10, y2=10)
    with pytest.raises(ValidationError):
        Detection(class_id=0, confidence=1.2, bbox=bbox)
    with pytest.raises(ValidationError):
        Detection(class_id=0, confidence=-0.1, bbox=bbox)


# --- AnglePerLight.distance_m >= 0 ----------------------------------------


def test_angle_per_light_negative_distance_rejected():
    with pytest.raises(ValidationError):
        AnglePerLight(runway_lamp=1, distance_m=-1.0, elevation_angle_deg=3.0)


def test_angle_per_light_zero_distance_accepted():
    angle = AnglePerLight(runway_lamp=1, distance_m=0.0, elevation_angle_deg=3.0)
    assert angle.distance_m == 0.0


# --- RunwayCreate runtime-registration guards (audit: runway CRUD validation) ----------


def _runway_lights(distinct: bool = True) -> list[dict]:
    lights = [
        {"point": 1, "latitude": 47.67352, "longitude": 9.51815, "altitude_m": 461.0},
        {"point": 2, "latitude": 47.67345, "longitude": 9.51821, "altitude_m": 461.0},
        {"point": 3, "latitude": 47.67338, "longitude": 9.51827, "altitude_m": 461.0},
        {"point": 4, "latitude": 47.67331, "longitude": 9.51833, "altitude_m": 461.0},
    ]
    if not distinct:  # collapse all four onto one position -> degenerate geometry
        for lamp in lights:
            lamp["latitude"], lamp["longitude"] = 47.67352, 9.51815
    return lights


def test_runway_create_rejects_blank_label():
    # min_length=1 still admits "   "; the store strips it to "" so the runway would
    # silently vanish on reload. The validator must reject blank-after-strip (audit).
    with pytest.raises(ValidationError):
        RunwayCreate(label="   ", lights=_runway_lights())


def test_runway_create_strips_label():
    runway = RunwayCreate(label="  Test PAPI 33  ", lights=_runway_lights())
    assert runway.label == "Test PAPI 33"


def test_runway_create_rejects_duplicate_lamp_coordinates():
    # Four identical positions make the per-lamp elevation angles meaningless (audit).
    with pytest.raises(ValidationError):
        RunwayCreate(label="Degenerate", lights=_runway_lights(distinct=False))
