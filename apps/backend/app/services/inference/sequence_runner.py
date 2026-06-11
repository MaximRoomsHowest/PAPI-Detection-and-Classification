"""Source-agnostic tracked-video core, shared by ``analyze_video`` (frames from a
``VideoCapture``) and ``analyze_frame_sequence`` (frames from a folder of images).

The YOLO call is injected as ``detect`` (bound to the service's loaded model +
device + confidence) so this module never imports the service — keeping the
dependency one-way (leaf -> service). Everything else it needs (writer, overlay,
aggregation, angle track, state) is a stateless leaf import.
"""

from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.services.angle import compute_elevation_angles
from app.services.inference.aggregation import aggregate_video_lamps
from app.services.inference.angle_resolver import build_angle_track
from app.services.inference.overlay import draw_overlay
from app.services.inference.video_writer import open_video_writer
from app.services.state import (
    DETECTION_CLASS_TO_STATE,
    confidence_from_lamps,
    detect_lamp_transitions,
    global_state_from_lamps,
    infer_single_missing_lamp_from_angle,
    normalize_detections,
    transition_events_from_state_runs,
)
from app.services.telemetry import DroneSample, resample_to_frames
from app.validation.schemas import AnalysisPayload, AngleResult, FramePoint


def _frame_angles_from_samples(
    drone_samples: list[DroneSample] | None,
    runway_id: str,
    frame_count: int | None,
) -> dict[int, float]:
    if not drone_samples or len(drone_samples) < 2 or not frame_count or frame_count <= 0:
        return {}

    angles: dict[int, float] = {}
    cache: dict[tuple[float, float, float], float | None] = {}
    for frame_index, sample in enumerate(resample_to_frames(drone_samples, frame_count)):
        key = (sample.latitude, sample.longitude, sample.altitude_m)
        if key not in cache:
            cache[key] = compute_elevation_angles(
                sample.latitude,
                sample.longitude,
                sample.altitude_m,
                runway_id,
            ).elevation_angle_deg
        if cache[key] is not None:
            angles[frame_index] = round(cache[key], 6)
    return angles


def run_tracked_sequence(
    frames,
    *,
    detect: Callable[..., list[dict]],
    cv2: Any,
    fps: float,
    width: int,
    height: int,
    runway_id: str,
    original_filename: str,
    drone_id: str | None,
    angle: AngleResult,
    start: float,
    max_frames: int,
    empty_message: str,
    exports_dir: Path,
    store_export: Callable[[Path], tuple[str, str]] | None = None,
    drone_samples: list[DroneSample] | None = None,
    transition_method: str = "tracking",
    expected_frame_count: int | None = None,
) -> AnalysisPayload:
    """Run ByteTrack detection per frame, write the annotated artifact, and aggregate
    the final per-lamp verdict + transitions by STABLE track identity.
    ``frames`` yields BGR frames already sized to ``width`` x ``height``.

    ``transition_method`` selects how transitions are derived from the SAME tracked observations:
    "tracking" = temporal red<->white flips (``detect_lamp_transitions``); "model" = learned
    class-2 transition-state runs (``transition_events_from_state_runs``, needs a 3-class model).

    ``store_export`` (when given) persists the finished artifact to the configured
    media backend and MUST return ``(reference, url)``: the storage reference that
    goes into the analysis-log row and the public URL for the payload. ``None``
    keeps the legacy local behaviour (``/media/<filename>``). The callable runs
    AFTER the writer is released, so a raising implementation leaves the local
    artifact on disk for the caller to clean up.
    """
    overlay_frame_angles = _frame_angles_from_samples(
        drone_samples,
        runway_id,
        expected_frame_count,
    )
    # ByteTrack id -> [(frame_index, color_state, center_x, confidence, redness)].
    # Drives BOTH temporal transition detection AND the final per-lamp verdict,
    # so both reference the same stable track identity (not per-frame rank).
    track_observations: dict[int, list[tuple]] = {}
    frame_count = 0
    last_detections: list[dict] = []
    # Raw per-frame verdict + confidence series (one entry per processed frame),
    # surfaced on the payload so the Live Demo can chart frame-by-frame confidence.
    per_frame: list[FramePoint] = []

    # Open the writer LAST before the try below, so nothing fallible runs between
    # acquiring it and the try/except that releases it (avoids a writer leak on an
    # init error between creation and the loop).
    base_path = exports_dir / f"{uuid4()}_annotated"
    writer, artifact_path = open_video_writer(cv2, base_path, fps, width, height)
    if writer is None:
        raise RuntimeError("Could not write annotated video artifact.")

    # The annotated artifact is partially written as the loop runs. If the loop
    # raises OR finishes with no readable frames, that partial file must NOT
    # survive as an orphan: release the writer AND unlink it before re-raising.
    # A successful (possibly truncated) run releases the writer and keeps the
    # artifact (audit: orphaned-annotated-artifact on max_frames exceeded).
    truncated_at_frame: int | None = None
    try:
        for frame in frames:
            if frame_count >= max_frames:
                # The source out-ran the limit mid-stream (container metadata lied
                # or was absent — honest sources are rejected up front). Failing
                # here would discard max_frames worth of paid inference; keep the
                # processed prefix and SAY SO on the payload instead (audit B2).
                truncated_at_frame = frame_count
                break

            # ByteTrack reset on the first frame so state from a previous
            # request doesn't bleed in (audit B-MAJ-1). Subsequent frames
            # continue with persist=True for actual tracking.
            detections = detect(
                frame,
                use_tracking=True,
                reset_tracker=(frame_count == 0),
            )
            lamps = normalize_detections(detections)
            # Record each tracked lamp's colour over time so red<->white
            # switches can be detected after the loop (transition is temporal,
            # not a per-frame geometric verdict).
            for det in detections:
                track_id = det.get("track_id")
                color = DETECTION_CLASS_TO_STATE.get(int(det.get("class_id", -1)))
                bbox = det.get("bbox")
                if track_id is None or color is None or not bbox:
                    continue
                center_x = (bbox["x1"] + bbox["x2"]) / 2
                # (frame, color, center_x, confidence, redness). The redness rides along so
                # the angle track can carry the per-frame Redness curve; downstream consumers
                # index the tuple or use *_, so the extra element is safe.
                track_observations.setdefault(int(track_id), []).append(
                    (frame_count, color, center_x, float(det.get("confidence", 0.0)), det.get("redness"))
                )
            frame_state = global_state_from_lamps(lamps)
            frame_confidence = confidence_from_lamps(lamps)
            # Raw per-frame sample (before the sliding-window smoothing used for
            # the overlay) — the genuine frame-to-frame confidence the UI plots.
            per_frame.append(
                FramePoint(frame_index=frame_count, confidence=frame_confidence, state=frame_state)
            )

            annotated = draw_overlay(
                cv2,
                frame,
                lamps,
                frame_state,
                frame_confidence,
                overlay_frame_angles.get(frame_count, angle.elevation_angle_deg),
            )
            writer.write(annotated)

            last_detections = detections
            frame_count += 1

        if frame_count == 0:
            raise ValueError(empty_message)
    except BaseException:
        # Any failure (too-long mid-loop, empty stream, or an unexpected error)
        # discards the half-written artifact instead of leaking it to disk.
        writer.release()
        artifact_path.unlink(missing_ok=True)
        raise
    else:
        writer.release()
    if store_export is not None:
        _artifact_ref, artifact_url = store_export(artifact_path)
    else:
        artifact_url = f"/media/{artifact_path.name}"

    final_lamps = infer_single_missing_lamp_from_angle(aggregate_video_lamps(track_observations), angle)
    global_state = global_state_from_lamps(final_lamps)
    confidence = confidence_from_lamps(final_lamps)
    # Per-frame angle track from the resolved telemetry (empty when no fixes or a
    # single fix): pairs each frame's viewing angle with the lamps seen there so
    # the chart can draw the real red<->white sweep. ``frame_angles`` then gives
    # each transition the angle AT its own frame (its commissioned set angle).
    angle_track, frame_angles = build_angle_track(
        drone_samples, runway_id, frame_count, track_observations
    )
    if transition_method == "model":
        transitions = transition_events_from_state_runs(
            track_observations, angle.elevation_angle_deg, frame_angles=frame_angles
        )
    else:
        transitions = detect_lamp_transitions(
            track_observations, angle.elevation_angle_deg, frame_angles=frame_angles
        )
    processing_ms = int((perf_counter() - start) * 1000)

    return AnalysisPayload(
        media_type="video",
        original_filename=original_filename,
        runway_id=runway_id,
        drone_id=drone_id,
        global_state=global_state,
        lamps=final_lamps,
        confidence=confidence,
        frame_count=frame_count,
        truncated_at_frame=truncated_at_frame,
        processing_ms=processing_ms,
        angle=angle,
        artifact_url=artifact_url,
        detections=last_detections,
        transitions=transitions,
        transition_method=transition_method,
        per_frame=per_frame,
        angle_track=angle_track,
    )
