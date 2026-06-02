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

# The only per-frame lamp states that represent a real detection the model made.
# A slot that is "obscured" (detector found nothing) or "unknown" (class fell
# outside the two-class map) carries no measured confidence, so these are the
# states that count when averaging confidence or judging a complete 4-lamp unit.
# Single source of truth shared by ``confidence_from_lamps`` and the obscured pad
# logic so the two can't drift on what "a real lamp reading" means.
DETECTED_LAMP_STATES = frozenset({"red", "white"})

# State assigned to a lamp slot the detector did not fill. Distinct from the
# generic "unknown" so the insights charts can surface "nothing detected here" as
# its own category instead of silently dropping the lamp. Carries no detection,
# hence confidence 0.0 and no bbox.
_OBSCURED_LAMP_STATE = "obscured"

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

    # Pad missing lamp slots so every verdict has exactly 4 entries. Each empty
    # slot is "obscured" (see _OBSCURED_LAMP_STATE) rather than the generic
    # "unknown", giving the insights charts a distinct "nothing detected here"
    # category instead of silently dropping the lamp.
    while len(lamps) < 4:
        lamps.append(
            LampResult(index=len(lamps) + 1, state=_OBSCURED_LAMP_STATE, confidence=0.0)
        )

    return lamps


# Tolerate this many frames between two observations of the same lamp when
# looking for a red<->white switch. >1 so a brief detector dropout / occlusion
# (routine at runtime, unlike the offline pipeline) can't silently drop a real
# transition.
TRANSITION_MAX_FRAME_GAP = 2


def lamp_index_by_track(track_observations: dict[int, list[tuple]]) -> dict[int, int]:
    """Map ByteTrack ids to lamp index 1..4 (left-to-right).

    The four real PAPI lamps are the most persistently tracked across a video; a
    transient false-positive track has few observations. So pick the four tracks
    with the most observations, then order them left-to-right by mean horizontal
    centre. SHARED by transition detection and the final video aggregation so both
    reference the same stable physical-lamp identity (a per-frame left-to-right
    rank scrambles the moment one frame drops or re-orders a lamp).
    """
    tracks = [(tid, obs) for tid, obs in track_observations.items() if tid is not None and obs]
    persistent = sorted(tracks, key=lambda kv: len(kv[1]), reverse=True)[:4]
    ordered = sorted(persistent, key=lambda kv: sum(o[2] for o in kv[1]) / len(kv[1]))
    return {tid: rank for rank, (tid, _) in enumerate(ordered, start=1)}


def detect_lamp_transitions(
    track_observations: dict[int, list[tuple]],
    elevation_angle_deg: float | None = None,
    frame_angles: dict[int, float] | None = None,
) -> list[TransitionEvent]:
    """Temporal red<->white transitions per ByteTrack-tracked lamp.

    ``track_observations`` maps a ByteTrack track id to its observed
    ``(frame_index, color_state, center_x, ...)`` tuples across a video. A
    transition is a red<->white change between two observations of the same lamp
    at most ``TRANSITION_MAX_FRAME_GAP`` frames apart. Lamps are numbered 1..4
    left-to-right via ``lamp_index_by_track`` (the same identity the final
    aggregation uses).

    Each event's viewing angle comes from ``frame_angles[frame_index]`` when a
    per-frame telemetry track is available (so a lamp that switches at frame 120
    gets the drone's angle AT frame 120 — the real set angle); otherwise it falls
    back to ``elevation_angle_deg`` (the single per-video value).
    """
    index_by_track = lamp_index_by_track(track_observations)

    def angle_at(frame_index: int) -> float | None:
        if frame_angles is not None and frame_index in frame_angles:
            return frame_angles[frame_index]
        return elevation_angle_deg

    events: list[TransitionEvent] = []
    for tid, obs in track_observations.items():
        lamp_index = index_by_track.get(tid)
        if lamp_index is None:
            continue
        ordered = sorted(obs, key=lambda item: item[0])
        for (frame_a, state_a, *_), (frame_b, state_b, *_) in zip(ordered, ordered[1:], strict=False):
            gap = frame_b - frame_a
            if gap <= 0 or gap > TRANSITION_MAX_FRAME_GAP:
                continue
            if state_a == state_b or {state_a, state_b} != {"red", "white"}:
                continue
            events.append(
                TransitionEvent(
                    lamp_index=lamp_index,
                    from_state=state_a,
                    to_state=state_b,
                    frame_index=frame_b,
                    elevation_angle_deg=angle_at(frame_b),
                )
            )
    events.sort(key=lambda event: (event.frame_index, event.lamp_index))
    return events


# Exact white-lamp count -> glidepath state for a complete 4-lamp PAPI unit.
# The five states are defined purely by how many lamps are white vs red, so this
# is an exact lookup, not a ratio. Mirrors the offline decoder
# (packages/papi/src/papi/global_state.py:derive_global_state) by construction.
_WHITE_COUNT_TO_STATE = {
    4: "far_too_high",       # 4 white
    3: "too_high",           # 3 white + 1 red
    2: "correct_glidepath",  # 2 white + 2 red
    1: "too_low",            # 1 white + 3 red
    0: "far_too_low",        # 4 red
}


def global_state_from_lamps(lamps: list[LampResult]) -> str:
    """Derive the 5-state global glidepath label (plus 'transition' / 'unknown').

    If any lamp is mid-transition the global state is 'transition'. Otherwise it
    is an exact white-count lookup over the four lamps; if fewer than four are
    confidently classified as white/red the state is 'unknown' rather than a guess
    from partial data (the previous ratio form silently invented a verdict for
    3-lamp inputs). Same outputs as the offline ``derive_global_state``.
    """
    if any(lamp.state == "transition" for lamp in lamps):
        return "transition"

    counts = Counter(lamp.state for lamp in lamps)
    detected_count = sum(counts[state] for state in DETECTED_LAMP_STATES)
    if detected_count != 4:
        return "unknown"
    return _WHITE_COUNT_TO_STATE.get(counts["white"], "unknown")


def confidence_from_lamps(lamps: list[LampResult]) -> float:
    """Mean detector confidence over the lamps that were actually detected.

    Only red/white lamps (``DETECTED_LAMP_STATES``) carry a real measurement;
    "obscured"/"unknown" slots have no detection behind them, so averaging them in
    would dilute the score toward zero. Returns 0.0 when nothing was detected.
    """
    detected = [lamp.confidence for lamp in lamps if lamp.state in DETECTED_LAMP_STATES]
    if not detected:
        return 0.0
    return round(sum(detected) / len(detected), 4)
