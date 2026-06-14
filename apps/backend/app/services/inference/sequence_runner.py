"""Source-agnostic tracked-video core, shared by ``analyze_video`` (frames from a
``VideoCapture``) and ``analyze_frame_sequence`` (frames from a folder of images).

The YOLO call is injected as ``detect`` (bound to the service's loaded model +
device + confidence) so this module never imports the service — keeping the
dependency one-way (leaf -> service). Everything else it needs (writer, overlay,
angle track, state) is a stateless leaf import.
"""

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.services.inference.angle_resolver import build_angle_track, frame_angle_map
from app.services.inference.overlay import draw_overlay
from app.services.inference.video_writer import open_video_writer
from app.services.state import (
    DETECTION_CLASS_TO_STATE,
    bind_lamps_to_runway_display,
    bind_transitions_to_runway_display,
    confidence_from_lamps,
    detect_lamp_transitions,
    frame_ranked_lamp_observations,
    global_state_from_lamps,
    normalize_detections,
    transition_events_from_state_runs,
)
from app.services.telemetry import DroneSample
from app.validation.schemas import (
    AnalysisPayload,
    AngleResult,
    BoundingBox,
    FrameLampState,
    FramePoint,
    LampResult,
)


def _frame_angles_from_samples(
    drone_samples: list[DroneSample] | None,
    runway_id: str,
    frame_count: int | None,
) -> dict[int, float]:
    # Delegates to the shared angle-resolver helper so the per-frame elevation map is
    # computed by ONE implementation. The overlay banner passes the mid-stream
    # expected frame count here; build_angle_track passes the actually-decoded count.
    return frame_angle_map(drone_samples, runway_id, frame_count)


def _frame_lamp_states(lamps) -> list[FrameLampState]:
    return [
        FrameLampState(
            index=lamp.index,
            state=lamp.state,
            confidence=lamp.confidence,
            redness=lamp.redness,
        )
        for lamp in lamps
        if 1 <= lamp.index <= 4
    ]


def _ranked_lamps_for_frame(
    ranked_observations: dict[int, list[tuple]],
    frame_index: int,
) -> list[LampResult]:
    by_lamp: dict[int, tuple] = {}
    for lamp_index, observations in ranked_observations.items():
        for observation in observations:
            if observation[0] == frame_index:
                by_lamp[lamp_index] = observation
                break

    lamps: list[LampResult] = []
    for lamp_index in range(1, 5):
        observation = by_lamp.get(lamp_index)
        if observation is None:
            lamps.append(LampResult(index=lamp_index, state="obscured", confidence=0.0))
            continue
        _frame, state, _center_x, confidence, *rest = observation
        redness = rest[0] if rest else None
        bbox = rest[1] if len(rest) > 1 else None
        lamps.append(
            LampResult(
                index=lamp_index,
                state=state,
                confidence=round(float(confidence), 4),
                bbox=BoundingBox(**bbox) if isinstance(bbox, dict) else None,
                redness=redness,
            )
        )
    return lamps


def _aggregate_ranked_lamps(ranked_observations: dict[int, list[tuple]]) -> list[LampResult]:
    """Summarize a video by all observed frames, not only the final frame."""
    lamps: list[LampResult] = []
    for lamp_index in range(1, 5):
        observations = ranked_observations.get(lamp_index, [])
        if not observations:
            lamps.append(LampResult(index=lamp_index, state="obscured", confidence=0.0))
            continue

        state = Counter(observation[1] for observation in observations).most_common(1)[0][0]
        matching = [observation for observation in observations if observation[1] == state]
        confidence = round(sum(float(observation[3]) for observation in matching) / len(matching), 4)
        redness_values = [
            float(observation[4])
            for observation in matching
            if len(observation) > 4 and observation[4] is not None
        ]
        bbox = next(
            (
                observation[5]
                for observation in reversed(matching)
                if len(observation) > 5 and isinstance(observation[5], dict)
            ),
            None,
        )
        lamps.append(
            LampResult(
                index=lamp_index,
                state=state,
                confidence=confidence,
                bbox=BoundingBox(**bbox) if bbox else None,
                redness=round(sum(redness_values) / len(redness_values), 4)
                if redness_values
                else None,
            )
        )
    return lamps


def _per_frame_points_from_ranked(
    ranked_observations: dict[int, list[tuple]],
    frame_count: int,
) -> list[FramePoint]:
    points: list[FramePoint] = []
    for frame_index in range(frame_count):
        lamps = _ranked_lamps_for_frame(ranked_observations, frame_index)
        points.append(
            FramePoint(
                frame_index=frame_index,
                confidence=confidence_from_lamps(lamps),
                state=global_state_from_lamps(lamps),
                lamps=_frame_lamp_states(lamps),
            )
        )
    return points


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
    shortfall_tolerance: int = 0,
) -> AnalysisPayload:
    """Run ByteTrack detection per frame, write the annotated artifact, and aggregate
    the final per-lamp verdict + transitions by display Light 1..4 slots.
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

    ``expected_frame_count`` + ``shortfall_tolerance`` drive the decode-shortfall
    contract: a source that yields MORE than ``expected_frame_count - tolerance``
    frames fewer than promised gets ``decode_shortfall`` stamped on the payload
    (a mid-stream decode failure reads like EOF, so without this a half-decoded
    file would present as a normal, complete, shorter analysis). The caller picks
    the tolerance because only it knows how trustworthy the count is: exact for
    an image list, approximate for video container metadata.
    """
    overlay_frame_angles = _frame_angles_from_samples(
        drone_samples,
        runway_id,
        expected_frame_count,
    )
    # ByteTrack id -> [(frame_index, color_state, center_x, confidence, redness)].
    # The post-loop transition paths convert this to per-frame left-to-right slots
    # before numbering lights, because tiny PAPI lamps can swap tracker ids.
    track_observations: dict[int, list[tuple]] = {}
    frame_count = 0
    last_detections: list[dict] = []
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
                # (frame, color, center_x, confidence, redness, bbox). Redness and
                # bbox ride along so the post-loop slot binding can build chart and
                # final-frame payloads from the same gap-preserving observations.
                track_observations.setdefault(int(track_id), []).append(
                    (
                        frame_count,
                        color,
                        center_x,
                        float(det.get("confidence", 0.0)),
                        det.get("redness"),
                        bbox,
                    )
                )
            current_ranked_observations = frame_ranked_lamp_observations(track_observations)
            raw_lamps = _ranked_lamps_for_frame(current_ranked_observations, frame_count)
            if not any(lamp.bbox is not None for lamp in raw_lamps):
                raw_lamps = normalize_detections(detections)
            lamps = bind_lamps_to_runway_display(raw_lamps, runway_id)
            frame_state = global_state_from_lamps(lamps)
            frame_confidence = confidence_from_lamps(lamps)
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

    # Decode shortfall: the source promised more frames than it delivered and we
    # did NOT stop on purpose (cap truncation above). Stamped past the caller's
    # tolerance so approximate video metadata doesn't cry wolf (audit 2026-06-12).
    decode_shortfall: int | None = None
    if truncated_at_frame is None and expected_frame_count:
        missing = expected_frame_count - frame_count
        if missing > max(0, shortfall_tolerance):
            decode_shortfall = missing

    # Per-frame angle track from the resolved telemetry (empty when no fixes or a
    # single fix): pairs each frame's viewing angle with the lamps seen there so
    # the chart can draw the real red<->white sweep. ``frame_angles`` then gives
    # each transition the angle AT its own frame (its commissioned set angle).
    ranked_observations = frame_ranked_lamp_observations(track_observations)
    per_frame = _per_frame_points_from_ranked(ranked_observations, frame_count)
    raw_angle_track, frame_angles = build_angle_track(
        drone_samples, runway_id, frame_count, track_observations
    )
    aggregate_lamps = bind_lamps_to_runway_display(_aggregate_ranked_lamps(ranked_observations), runway_id)
    global_state = global_state_from_lamps(aggregate_lamps)
    confidence = confidence_from_lamps(aggregate_lamps)
    angle_track = [
        sample.model_copy(
            update={"lamps": bind_lamps_to_runway_display(sample.lamps, runway_id)}
        )
        for sample in raw_angle_track
    ]
    if transition_method == "model":
        raw_transitions = transition_events_from_state_runs(
            ranked_observations, angle.elevation_angle_deg, frame_angles=frame_angles
        )
    else:
        raw_transitions = detect_lamp_transitions(
            ranked_observations,
            angle.elevation_angle_deg,
            frame_angles=frame_angles,
        )
    transitions = bind_transitions_to_runway_display(raw_transitions, runway_id)
    processing_ms = int((perf_counter() - start) * 1000)

    return AnalysisPayload(
        media_type="video",
        original_filename=original_filename,
        runway_id=runway_id,
        drone_id=drone_id,
        global_state=global_state,
        lamps=aggregate_lamps,
        confidence=confidence,
        frame_count=frame_count,
        truncated_at_frame=truncated_at_frame,
        decode_shortfall=decode_shortfall,
        processing_ms=processing_ms,
        angle=angle,
        artifact_url=artifact_url,
        detections=last_detections,
        transitions=transitions,
        transition_method=transition_method,
        per_frame=per_frame,
        angle_track=angle_track,
    )
