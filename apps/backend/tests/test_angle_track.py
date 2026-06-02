"""Per-frame angle track + telemetry-file plumbing.

Covers the pieces the metadata-file feature added on top of the parser:
  * ``InferenceService._build_angle_track`` — aligns a telemetry track to frames,
    computes a per-frame midpoint angle, and tags each frame with the lamps seen
    there (stable identity) so the chart can draw the red->white sweep,
  * ``detect_lamp_transitions(frame_angles=...)`` — each transition gets the angle
    AT its own frame (its commissioned set angle),
  * ``_angle_from_samples`` / ``_resolve_drone_samples`` — representative angle +
    source priority (file > manual > EXIF),
  * the ``read_metadata_samples`` endpoint helper — parses an upload, 400 on garbage.

The model is never loaded: ``InferenceService.__init__`` is lazy and none of these
methods touch YOLO/cv2.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

# Import app.main first so the api.routes <-> api.routers import order is fully
# resolved before we pull a symbol straight out of the analyze router module
# (importing it cold otherwise hits a partially-initialised-package cycle).
import app.main  # noqa: F401  (bootstraps the router package import order)
from app.api.routers.analyze import read_metadata_samples
from app.config import get_settings
from app.services.inference import InferenceService
from app.services.state import detect_lamp_transitions
from app.services.telemetry import DroneSample

RUNWAY = "papi_24"


@pytest.fixture
def service() -> InferenceService:
    # Cheap: __init__ only stores settings + a lock; the model stays unloaded.
    return InferenceService(get_settings())


def _descent_samples(n: int = 10) -> list[DroneSample]:
    # North of the EDNY rwy-24 PAPI, descending — the viewing angle shrinks per frame.
    return [
        DroneSample(47.6798 - i * 0.00015, 9.5181 + i * 0.00001, 520.0 - i * 4.0, frame_index=i)
        for i in range(n)
    ]


def _track_observations() -> dict[int, list[tuple]]:
    """Four lamps left-to-right by center_x; lamp 3 switches red->white at frame 5."""

    def obs(states: list[str], center_x: float) -> list[tuple]:
        return [(frame, state, center_x, 0.9) for frame, state in enumerate(states)]

    return {
        10: obs(["white"] * 10, 100.0),  # -> lamp 1
        20: obs(["white"] * 10, 200.0),  # -> lamp 2
        30: obs(["red"] * 5 + ["white"] * 5, 300.0),  # -> lamp 3 (transition @ frame 5)
        40: obs(["red"] * 10, 400.0),  # -> lamp 4
    }


# --- _build_angle_track ------------------------------------------------------


def test_build_angle_track_sweeps_angle_and_carries_lamp_states(service: InferenceService) -> None:
    samples = _descent_samples(10)
    track, frame_angles = service._build_angle_track(samples, RUNWAY, frame_count=10, track_observations=_track_observations())

    # One angle per frame; angles shrink monotonically as the drone descends.
    assert len(frame_angles) == 10
    angles = [frame_angles[i] for i in range(10)]
    assert angles[0] > angles[-1]
    assert angles == sorted(angles, reverse=True)

    # 10 frames < cap -> no downsampling; every sample lists all four lamps.
    assert len(track) == 10
    assert {lamp.index for lamp in track[0].lamps} == {1, 2, 3, 4}

    def state_of(sample, lamp_index: int) -> str:
        return next(lamp.state for lamp in sample.lamps if lamp.index == lamp_index)

    # The sweep: lamp 3 reads red early and white late.
    assert state_of(track[0], 3) == "red"
    assert state_of(track[9], 3) == "white"


def test_build_angle_track_empty_for_single_fix(service: InferenceService) -> None:
    track, frame_angles = service._build_angle_track(
        [DroneSample(47.0, 9.0, 500.0)], RUNWAY, frame_count=10, track_observations={}
    )
    assert track == [] and frame_angles == {}


def test_build_angle_track_empty_without_samples(service: InferenceService) -> None:
    assert service._build_angle_track(None, RUNWAY, 10, {}) == ([], {})


# --- per-frame transition angle ---------------------------------------------


def test_transition_uses_angle_at_its_own_frame(service: InferenceService) -> None:
    samples = _descent_samples(10)
    observations = _track_observations()
    _, frame_angles = service._build_angle_track(samples, RUNWAY, 10, observations)

    events = detect_lamp_transitions(observations, elevation_angle_deg=None, frame_angles=frame_angles)
    lamp3 = [event for event in events if event.lamp_index == 3]
    assert lamp3, "expected a red->white transition on lamp 3"
    assert lamp3[0].to_state == "white" and lamp3[0].frame_index == 5
    # The event carries the viewing angle AT frame 5, not a single per-clip value.
    assert lamp3[0].elevation_angle_deg == pytest.approx(frame_angles[5])


def test_transition_falls_back_to_single_angle_without_track() -> None:
    observations = _track_observations()
    events = detect_lamp_transitions(observations, elevation_angle_deg=3.2)
    lamp3 = [event for event in events if event.lamp_index == 3]
    assert lamp3 and lamp3[0].elevation_angle_deg == pytest.approx(3.2)


# --- representative angle + source priority ---------------------------------


def test_angle_from_samples_unavailable_when_empty(service: InferenceService) -> None:
    result = service._angle_from_samples([], None, RUNWAY)
    assert result.angle_available is False


def test_angle_from_samples_uses_middle_fix(service: InferenceService) -> None:
    result = service._angle_from_samples(_descent_samples(10), "telemetry_file", RUNWAY)
    assert result.angle_available is True
    assert result.angle_source == "telemetry_file"
    assert result.elevation_angle_deg is not None


def test_resolve_drone_samples_priority_order() -> None:
    missing = Path("does-not-exist.jpg")
    samples = [DroneSample(47.0, 9.0, 500.0)]

    resolved, source = InferenceService._resolve_drone_samples(missing, (47.5, 9.5, 480.0), samples)
    assert source == "telemetry_file" and resolved is samples  # file beats manual

    resolved, source = InferenceService._resolve_drone_samples(missing, (47.5, 9.5, 480.0), None)
    assert source == "request_metadata" and len(resolved) == 1  # manual beats (absent) EXIF

    resolved, source = InferenceService._resolve_drone_samples(missing, None, None)
    assert resolved is None and source is None  # nothing usable -> angle unavailable


def test_evenly_spaced_downsamples_with_endpoints() -> None:
    assert InferenceService._evenly_spaced([0, 1, 2, 3], 10) == [0, 1, 2, 3]  # under cap: unchanged
    picked = InferenceService._evenly_spaced(list(range(100)), 5)
    assert len(picked) <= 5
    assert picked[0] == 0 and picked[-1] == 99  # endpoints preserved


# --- read_metadata_samples (endpoint helper) --------------------------------


def _upload(name: str, raw: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(raw))


def test_read_metadata_samples_none_and_empty() -> None:
    assert read_metadata_samples(None) is None
    assert read_metadata_samples(_upload("e.srt", b"   ")) is None


def test_read_metadata_samples_parses_srt() -> None:
    raw = b"1\n00:00:00,000 --> 00:00:00,033\n[latitude: 47.6] [longitude: 9.5] [abs_alt: 520]\n"
    samples = read_metadata_samples(_upload("t.srt", raw))
    assert samples is not None and len(samples) == 1
    assert samples[0].altitude_m == pytest.approx(520.0)


def test_read_metadata_samples_garbage_is_400() -> None:
    with pytest.raises(HTTPException) as excinfo:
        read_metadata_samples(_upload("g.csv", b"just prose, no fixes\n"))
    assert excinfo.value.status_code == 400
