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
    # Forward-compatible with the 3-class transition-aware model (branch transition-model):
    # such a model emits class 2 directly, so a single frame CAN read "transition". The live
    # 2-class model never produces class 2, so this entry is inert for it (no behaviour change).
    # The temporal red<->white method below (detect_lamp_transitions) remains the path for
    # 2-class models; aggregate_transition_state_events is the path for a 3-class model.
    2: "transition",
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


# A genuine transition state run must persist at least this many observed frames; a single
# isolated "transition" frame is treated as detector flicker and dropped (temporal smoothing).
MIN_TRANSITION_RUN_FRAMES = 1


def _transition_event(eid: int, lamp_index: int, run: list[int], before: str | None,
                      after: str | None, frame_angles: dict[int, float] | None) -> dict:
    angles = frame_angles or {}
    start, end = run[0], run[-1]
    return {
        "transition_event_id": f"L{lamp_index}-E{eid}",
        "lamp_index": lamp_index,
        "start_frame": start,
        "end_frame": end,
        "duration_frames": end - start + 1,
        "from_state": before,
        "to_state": after,
        "start_angle_deg": angles.get(start),
        "end_angle_deg": angles.get(end),
    }


def aggregate_transition_state_events(
    track_observations: dict[int, list[tuple]],
    frame_angles: dict[int, float] | None = None,
    min_run_frames: int = MIN_TRANSITION_RUN_FRAMES,
) -> list[dict]:
    """Group runs of per-frame "transition" state (from a 3-class model) into per-lamp events.

    For a transition-aware detector a lamp reads "transition" for a short run of frames around a
    red<->white switch. This collapses each maximal run into ONE event with a stable id, frame
    span, duration, and the bracketing stable colours (the per-lamp transition events the frontend
    counts), applying a minimum-run filter so a one-frame flicker is not reported. Returns [] for a
    2-class model (no "transition" states ever appear). Lamp identity uses the same
    ``lamp_index_by_track`` as the temporal method so both reference one physical-lamp numbering.
    """
    index_by_track = lamp_index_by_track(track_observations)
    events: list[dict] = []
    eid = 0
    for tid, obs in track_observations.items():
        lamp_index = index_by_track.get(tid)
        if lamp_index is None:
            continue
        ordered = sorted(obs, key=lambda item: item[0])
        last_stable: str | None = None
        run: list[int] = []
        for frame, state, *_ in ordered:
            if state == "transition":
                run.append(frame)
                continue
            if len(run) >= min_run_frames:
                eid += 1
                events.append(_transition_event(eid, lamp_index, run, last_stable, state, frame_angles))
            run = []
            last_stable = state
        if len(run) >= min_run_frames:
            eid += 1
            events.append(_transition_event(eid, lamp_index, run, last_stable, None, frame_angles))
    events.sort(key=lambda e: (e["start_frame"], e["lamp_index"]))
    return events


def transition_events_from_state_runs(
    track_observations: dict[int, list[tuple]],
    elevation_angle_deg: float | None = None,
    frame_angles: dict[int, float] | None = None,
) -> list[TransitionEvent]:
    """The "model" transition method: per-lamp ``TransitionEvent``s from a 3-class model's class-2 runs.

    Each maximal run of per-frame "transition" state (``aggregate_transition_state_events``) that is
    bracketed by two stable colours becomes one event (``method="model"``) carrying the run's span +
    duration. Incomplete runs (a lamp still transitioning at the track edge) are skipped so
    ``from_state``/``to_state`` stay red/white. Returns [] for a 2-class model. The viewing angle is
    the drone's angle at the run's start frame when a per-frame track is available, else the single
    representative angle — mirroring ``detect_lamp_transitions`` (the "tracking" method).
    """
    events: list[TransitionEvent] = []
    for run in aggregate_transition_state_events(track_observations, frame_angles):
        from_state, to_state = run["from_state"], run["to_state"]
        if from_state not in ("red", "white") or to_state not in ("red", "white"):
            continue
        start = run["start_frame"]
        angle = run["start_angle_deg"]
        if angle is None:
            angle = (frame_angles or {}).get(start, elevation_angle_deg)
        events.append(
            TransitionEvent(
                lamp_index=run["lamp_index"],
                from_state=from_state,
                to_state=to_state,
                frame_index=start,
                elevation_angle_deg=angle,
                method="model",
                transition_event_id=run["transition_event_id"],
                start_frame=start,
                end_frame=run["end_frame"],
                duration_frames=run["duration_frames"],
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
