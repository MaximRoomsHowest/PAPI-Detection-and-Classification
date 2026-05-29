"""Per-lamp + global state derivation for the backend API.

Detection-class IDs from the YOLO model are 0=red, 1=white, so a lamp's
per-frame state is only ever red / white / unknown. The third label,
"transition", is NOT a per-frame verdict: per the project design
(docs/label_spec.md, "transition handling moved to the temporal tracking
layer") it is a *temporal* red<->white change observed by tracking a lamp
across consecutive frames. ``detect_lamp_transitions`` produces those events
from ByteTrack-tracked detections; the drone-metadata elevation angle is
associated with each event (it annotates the transition, it does not decide it).
"""

from collections import Counter

from app.validation.schemas import BoundingBox, LampResult, TransitionEvent

DETECTION_CLASS_TO_STATE = {
    0: "red",
    1: "white",
}

GLOBAL_STATE_LABELS = {
    "far_too_high": "Far too high",
    "too_high": "Too high",
    "correct_glidepath": "Correct glidepath",
    "too_low": "Too low",
    "far_too_low": "Far too low",
    "transition": "Transition",
    "unknown": "Unknown",
}


def normalize_detections(raw_detections: list[dict]) -> list[LampResult]:
    """Build per-lamp results (red/white) sorted left-to-right.

    Transition is deliberately NOT decided here: a single frame can only show a
    lamp as red, white, or unknown. A "transition" is a red<->white switch
    observed over time -- see ``detect_lamp_transitions``.
    """
    candidates = []
    for detection in raw_detections:
        state = DETECTION_CLASS_TO_STATE.get(int(detection.get("class_id", -1)), "unknown")
        bbox = detection.get("bbox")
        if not bbox:
            continue
        confidence = float(detection.get("confidence", 0.0))
        center_x = (bbox["x1"] + bbox["x2"]) / 2
        candidates.append((center_x, confidence, state, bbox))

    candidates = sorted(candidates, key=lambda item: item[1], reverse=True)[:4]
    candidates = sorted(candidates, key=lambda item: item[0])

    lamps: list[LampResult] = []
    for index, (_, confidence, state, bbox) in enumerate(candidates, start=1):
        lamps.append(
            LampResult(
                index=index,
                state=state,
                confidence=confidence,
                bbox=BoundingBox(**bbox),
            )
        )

    while len(lamps) < 4:
        lamps.append(LampResult(index=len(lamps) + 1, state="unknown", confidence=0.0))

    return lamps


def detect_lamp_transitions(
    track_observations: dict[int, list[tuple[int, str, float]]],
    elevation_angle_deg: float | None = None,
) -> list[TransitionEvent]:
    """Temporal red<->white transitions per ByteTrack-tracked lamp.

    ``track_observations`` maps a ByteTrack track id to its observed
    ``(frame_index, color_state, center_x)`` tuples across a video. A transition
    is a red<->white change between two *consecutive* frames of the same track
    (mirrors the offline ``papi.tracking.detect_transitions`` so the live API and
    the dataset pipeline agree). Tracks are numbered 1..4 left-to-right by their
    average horizontal position; ``elevation_angle_deg`` (one value per uploaded
    video) is attached to each event.
    """
    tracks = {
        tid: obs
        for tid, obs in track_observations.items()
        if tid is not None and len(obs) >= 2
    }
    ranked = sorted(tracks.items(), key=lambda kv: sum(o[2] for o in kv[1]) / len(kv[1]))
    lamp_index_by_track = {tid: rank for rank, (tid, _) in enumerate(ranked[:4], start=1)}

    events: list[TransitionEvent] = []
    for tid, obs in tracks.items():
        lamp_index = lamp_index_by_track.get(tid)
        if lamp_index is None:
            continue
        ordered = sorted(obs, key=lambda item: item[0])
        for (frame_a, state_a, _), (frame_b, state_b, _) in zip(ordered, ordered[1:], strict=False):
            if frame_b != frame_a + 1:
                continue
            if state_a == state_b or {state_a, state_b} != {"red", "white"}:
                continue
            events.append(
                TransitionEvent(
                    lamp_index=lamp_index,
                    from_state=state_a,
                    to_state=state_b,
                    frame_index=frame_b,
                    elevation_angle_deg=elevation_angle_deg,
                )
            )
    events.sort(key=lambda event: (event.frame_index, event.lamp_index))
    return events


def global_state_from_lamps(lamps: list[LampResult]) -> str:
    """Derive the 5-state global glidepath label (plus 'transition' / 'unknown').

    A lamp in transition shadows the five nominal states: if *any* lamp is in
    transition, the global state is "transition". Matches
    ``packages/papi/src/papi/global_state.py:derive_global_state``.
    """
    if any(lamp.state == "transition" for lamp in lamps):
        return "transition"

    counts = Counter(lamp.state for lamp in lamps)
    known_count = counts["white"] + counts["red"]

    if known_count < 4:
        return "unknown"

    white_ratio = counts["white"] / known_count
    if white_ratio >= 0.85:
        return "far_too_high"
    if 0.60 <= white_ratio < 0.85:
        return "too_high"
    if 0.40 <= white_ratio < 0.60:
        return "correct_glidepath"
    if 0.15 <= white_ratio < 0.40:
        return "too_low"
    return "far_too_low"


def confidence_from_lamps(lamps: list[LampResult]) -> float:
    known = [lamp.confidence for lamp in lamps if lamp.state != "unknown"]
    if not known:
        return 0.0
    return round(sum(known) / len(known), 4)
