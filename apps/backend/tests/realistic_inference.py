"""Realistic fake InferenceService payloads for integration tests.

test_integration.py stubs inference with one fixed happy-path payload (4 lamps,
no detections, no per-frame data). That covers route wiring but not the parts
of the contract the frontend actually consumes for videos: ``per_frame``,
``transitions``, ``angle_track``, ``truncated_at_frame``, and detections with
bboxes/track ids. The builders here produce payloads with those shapes filled
the way the real service fills them — deterministically (no RNG; reruns must
not flake) — so round-trip tests can pin that the full contract survives the
HTTP layer, DB persistence, and the CSV export.

Field names mirror app/validation/schemas/{analysis,angle,lamp}.py exactly;
pydantic validation at construction time keeps this module honest if the
schema evolves.
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock

from app.services.inference import InferenceService
from app.validation.schemas import (
    AnalysisPayload,
    AngleResult,
    AngleSample,
    Detection,
    FrameLampState,
    FramePoint,
    LampResult,
    ModelInfo,
    TransitionEvent,
)

# Left-to-right lamp boxes roughly matching a 1280x720 frame's PAPI bar.
_LAMP_BBOXES = [
    {"x1": 312, "y1": 396, "x2": 332, "y2": 414},
    {"x1": 472, "y1": 398, "x2": 491, "y2": 415},
    {"x1": 633, "y1": 397, "x2": 651, "y2": 413},
    {"x1": 794, "y1": 399, "x2": 812, "y2": 416},
]
_LAMP_CONFIDENCES = (0.96, 0.91, 0.88, 0.83)


def _angle_result(angle: str | None) -> AngleResult:
    """An AngleResult variant per telemetry source ('manual'|'exif'|'file'|None)."""
    if angle is None:
        return AngleResult(
            angle_available=False,
            angle_note="No drone position was supplied or readable from the upload.",
        )
    source = {
        "manual": "request_metadata",
        "exif": "file_metadata",
        "file": "telemetry_file",
    }[angle]
    return AngleResult(
        angle_available=True,
        elevation_angle_deg=3.02,
        angle_source=source,
        angle_note=f"Angle computed from {source}.",
        plausible=True,
        nearest_lamp_distance_m=412.6,
    )


def _lamps(lamp_states: tuple[str, ...]) -> list[LampResult]:
    return [
        LampResult(
            index=i + 1,
            state=state,
            confidence=_LAMP_CONFIDENCES[i % len(_LAMP_CONFIDENCES)],
            bbox=_LAMP_BBOXES[i % len(_LAMP_BBOXES)],
            redness=200.0 if state == "red" else 35.0,
        )
        for i, state in enumerate(lamp_states)
    ]


def _detections(lamp_states: tuple[str, ...], tracked: bool) -> list[Detection]:
    return [
        Detection(
            class_id=0 if state == "red" else 1,
            confidence=_LAMP_CONFIDENCES[i % len(_LAMP_CONFIDENCES)],
            bbox=_LAMP_BBOXES[i % len(_LAMP_BBOXES)],
            track_id=(i + 1) if tracked else None,
            redness=200.0 if state == "red" else 35.0,
        )
        for i, state in enumerate(lamp_states)
    ]


def realistic_image_payload(
    *,
    runway_id: str,
    original_filename: str,
    model_id: str = "small",
    lamp_states: tuple[str, ...] = ("white", "white", "red", "red"),
    angle: str | None = None,
) -> AnalysisPayload:
    """A single-image payload shaped like the real service's output."""
    lamps = _lamps(lamp_states)
    return AnalysisPayload(
        media_type="image",
        original_filename=original_filename,
        runway_id=runway_id,
        model_id=model_id,
        model_label="Small detector",
        model_role="detector",
        global_state="correct_glidepath",
        lamps=lamps,
        confidence=round(sum(lamp.confidence for lamp in lamps) / len(lamps), 4),
        frame_count=1,
        processing_ms=317,
        angle=_angle_result(angle),
        artifact_url=f"/media/exports/{original_filename}.annotated.png",
        detections=_detections(lamp_states, tracked=False),
    )


def realistic_video_payload(
    *,
    runway_id: str,
    original_filename: str,
    model_id: str = "small",
    frame_count: int = 48,
    with_transitions: bool = True,
    with_angle_track: bool = False,
    truncated: bool = False,
) -> AnalysisPayload:
    """A video payload with a deterministic per-frame series.

    The confidence curve is a smooth wobble (sin-based, no RNG) with a couple of
    low-confidence ``unknown`` dips, mirroring how a real descent sweep looks.
    ``truncated=True`` stamps ``truncated_at_frame == frame_count``: the limit
    was hit mid-stream, frames [0, frame_count) were kept.
    """
    per_frame = []
    for i in range(frame_count):
        confidence = round(0.8 + 0.12 * math.sin(i / 3), 4)
        dip = i in (frame_count // 4, frame_count // 4 + 1)
        per_frame.append(
            FramePoint(
                frame_index=i,
                confidence=0.18 if dip else confidence,
                state="unknown" if dip else "correct_glidepath",
            )
        )

    transitions = []
    if with_transitions:
        mid = frame_count // 2
        transitions.append(
            TransitionEvent(
                lamp_index=2,
                from_state="red",
                to_state="white",
                frame_index=mid,
                elevation_angle_deg=3.18 if with_angle_track else None,
                method="tracking",
            )
        )

    angle_track = []
    if with_angle_track:
        for i in range(0, frame_count, 4):
            angle_track.append(
                AngleSample(
                    frame_index=i,
                    # Descending approach: the viewing angle eases from ~3.4° to ~2.8°.
                    elevation_angle_deg=round(3.4 - (0.6 * i / max(1, frame_count - 1)), 3),
                    lamps=[
                        FrameLampState(index=1, state="white", confidence=0.95),
                        FrameLampState(index=2, state="white" if i >= frame_count // 2 else "red", confidence=0.9),
                        FrameLampState(index=3, state="red", confidence=0.88),
                        FrameLampState(index=4, state="red", confidence=0.85),
                    ],
                )
            )

    lamp_states = ("white", "white", "red", "red")
    return AnalysisPayload(
        media_type="video",
        original_filename=original_filename,
        runway_id=runway_id,
        model_id=model_id,
        model_label="Small detector",
        model_role="detector",
        global_state="correct_glidepath",
        lamps=_lamps(lamp_states),
        confidence=0.87,
        frame_count=frame_count,
        truncated_at_frame=frame_count if truncated else None,
        processing_ms=frame_count * 320,
        angle=_angle_result("file" if with_angle_track else None),
        artifact_url=f"/media/exports/{original_filename}.annotated.webm",
        detections=_detections(lamp_states, tracked=True),
        transitions=transitions,
        transition_method="tracking",
        per_frame=per_frame,
        angle_track=angle_track,
    )


def make_realistic_inference_service(tmp_path, **video_kwargs) -> MagicMock:
    """A MagicMock(spec=InferenceService) wired like test_integration.py's stub,
    but answering with the realistic builders above: images via ``analyze`` with
    media_type='image', videos via ``analyze`` with media_type='video' (using
    ``video_kwargs``), folder sequences via ``analyze_frame_sequence``.
    """
    fake_service = MagicMock(spec=InferenceService)

    def _analyze(
        media_path,
        media_type,
        runway_id,
        original_filename,
        drone_id=None,
        drone_metadata=None,
        drone_samples=None,
        transition_method=None,
        model_id=None,
    ):
        if media_type == "video":
            return realistic_video_payload(
                runway_id=runway_id,
                original_filename=original_filename,
                model_id=model_id or "small",
                **video_kwargs,
            )
        return realistic_image_payload(
            runway_id=runway_id,
            original_filename=original_filename,
            model_id=model_id or "small",
            angle="manual" if drone_metadata else None,
        )

    def _analyze_sequence(
        image_paths, runway_id, original_filename, drone_id=None, drone_metadata=None,
        drone_samples=None, transition_method=None, model_id=None,
    ):
        return realistic_video_payload(
            runway_id=runway_id,
            original_filename=original_filename,
            model_id=model_id or "small",
            frame_count=len(image_paths),
            **{k: v for k, v in video_kwargs.items() if k != "frame_count"},
        )

    fake_service.analyze.side_effect = _analyze
    fake_service.analyze_frame_sequence.side_effect = _analyze_sequence
    fake_service.is_loaded = True
    fake_service.default_weights_present = True
    fake_service.model_info.return_value = ModelInfo(
        model_id="small",
        model_label="Small detector",
        model_role="detector",
        is_default=True,
        model_path=str(tmp_path / "models" / "best.pt"),
        model_filename="best.pt",
        model_format="pt",
        backend_type="ultralytics-pytorch",
        exists=True,
        file_size_mb=12.5,
        confidence_threshold=0.4,
        device="cpu",
        loaded=False,
    )
    fake_service.model_options.return_value = [fake_service.model_info.return_value]
    return fake_service
