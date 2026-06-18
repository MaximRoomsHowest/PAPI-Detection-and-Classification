"""Per-lamp + global state derivation for the backend API.

The canonical detector classes are 0=red and 1=white. The optional experimental
3-class model can also emit 2=transition during a video run, but a transition
event is still accepted only when temporal evidence brackets that state with a
real red<->white change. ``detect_lamp_transitions`` produces tracking-method
events from red/white observations; ``transition_events_from_state_runs`` does
the equivalent collapse for class-2 runs. The drone-metadata elevation angle is
associated with each event; it annotates the transition, it does not decide it.
"""

from collections import Counter

from papi.global_state import WHITE_COUNT_TO_CODE
from papi.lamp_state import FAA_DEFAULT_SET_ANGLES_DEG

from app.validation.schemas import AngleResult, BoundingBox, LampResult, TransitionEvent

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

# Runtime fallback for angle-based inference when one lamp slot is missing. The set-angle
# values are single-sourced from papi.lamp_state.FAA_DEFAULT_SET_ANGLES_DEG (imported above) —
# used here deliberately as a SET, not a per-slot binding: which image slot carries which set
# angle flips with the approach direction (rwy 06 vs 24 view the same array from opposite
# sides), and the EDNY transition data shows image-lamp 1 flipping at ~3.43 deg on rwy 24 — the
# reverse of the config-comment convention. Inference therefore only uses the COUNT of set
# angles below the viewing angle, never a slot-indexed lookup (see
# infer_single_missing_lamp_from_angle).
TRANSITION_HALF_WIDTH_DEG = 0.10


def normalize_detections(raw_detections: list[dict]) -> list[LampResult]:
    """Build per-lamp results (red/white) sorted left-to-right.

    Transition events are deliberately NOT decided here: a single detection is
    only a state sample. Red/white switches are emitted later by temporal logic.
    """
    candidates = []
    for detection in raw_detections:
        state = DETECTION_CLASS_TO_STATE.get(int(detection.get("class_id", -1)), "unknown")
        bbox = detection.get("bbox")
        if not bbox:
            continue
        confidence = float(detection.get("confidence", 0.0))
        center_x = (bbox["x1"] + bbox["x2"]) / 2
        candidates.append((center_x, confidence, state, bbox, detection.get("redness")))

    candidates = sorted(candidates, key=lambda item: item[1], reverse=True)[:4]
    candidates = sorted(candidates, key=lambda item: item[0])

    lamps: list[LampResult] = []
    for index, (_, confidence, state, bbox, redness) in enumerate(candidates, start=1):
        lamps.append(
            LampResult(
                index=index,
                state=state,
                confidence=confidence,
                bbox=BoundingBox(**bbox),
                redness=redness,
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


def display_lamp_index(runway_id: str, lamp_index: int) -> int:
    """Map internal tracked index to the user-facing lamp number.

    Rodrigo's UI convention is image left-to-right: Light 1, Light 2, Light 3,
    Light 4. Runtime tracking already assigns indices by image x-position, so
    this is currently an identity mapping for all configured runways.
    """
    return lamp_index


def bind_lamps_to_runway_display(lamps: list[LampResult], runway_id: str) -> list[LampResult]:
    """Return lamps sorted by user-facing index for the selected runway."""
    return sorted(
        (lamp.model_copy(update={"index": display_lamp_index(runway_id, lamp.index)}) for lamp in lamps),
        key=lambda lamp: lamp.index,
    )


def bind_transitions_to_runway_display(
    transitions: list[TransitionEvent],
    runway_id: str,
) -> list[TransitionEvent]:
    """Return transition events with lamp_index in user-facing runway order."""
    return sorted(
        (
            event.model_copy(
                update={"lamp_index": display_lamp_index(runway_id, event.lamp_index)}
            )
            for event in transitions
        ),
        key=lambda event: (event.frame_index, event.lamp_index),
    )


def denoise_track_observations(
    track_observations: dict[int, list[tuple]],
    max_frame_gap: int = TRANSITION_MAX_FRAME_GAP,
) -> dict[int, list[tuple]]:
    """Collapse one-frame colour blips inside each tracked lamp.

    Runtime detections occasionally produce an isolated ``red/white/red`` or
    ``white/red/white`` sample for a stable lamp. Those should not become two
    transition events, but endpoints and sustained changes are left intact.
    """
    stabilized: dict[int, list[tuple]] = {}
    for track_id, observations in track_observations.items():
        ordered = sorted(observations, key=lambda item: item[0])
        if len(ordered) < 3:
            stabilized[track_id] = ordered
            continue
        cleaned = list(ordered)
        for index in range(1, len(ordered) - 1):
            # Read prev from the partially-corrected list, not the original: otherwise a
            # consecutive alternating run (R W R W R) chains into a phantom isolated W,
            # emitting spurious transition events from a steady lamp (audit).
            prev = cleaned[index - 1]
            current = ordered[index]
            next_obs = ordered[index + 1]
            prev_frame, prev_state = prev[0], prev[1]
            frame, state = current[0], current[1]
            next_frame, next_state = next_obs[0], next_obs[1]
            if (
                state != prev_state
                and prev_state == next_state
                and 0 < frame - prev_frame <= max_frame_gap
                and 0 < next_frame - frame <= max_frame_gap
            ):
                cleaned[index] = (frame, prev_state, *current[2:])
        stabilized[track_id] = cleaned
    return stabilized


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


def _reference_slot_centers(observations_by_frame: dict[int, list[tuple]]) -> list[float] | None:
    complete_frames: list[list[tuple]] = []
    for observations in observations_by_frame.values():
        top_four = sorted(observations, key=lambda item: item[3], reverse=True)[:4]
        if len(top_four) == 4:
            complete_frames.append(sorted(top_four, key=lambda item: item[2]))
    if not complete_frames:
        return None
    return [
        sum(frame[slot][2] for frame in complete_frames) / len(complete_frames)
        for slot in range(4)
    ]


def _assign_observations_to_slots(
    observations: list[tuple],
    reference_centers: list[float] | None,
) -> list[tuple[int, tuple]]:
    """Assign frame detections to Light 1..4 without compacting across missing slots."""
    top_four = sorted(observations, key=lambda item: item[3], reverse=True)[:4]
    ordered = sorted(top_four, key=lambda item: item[2])
    if reference_centers is None or len(ordered) == 4:
        return list(enumerate(ordered, start=1))

    # Pick the monotonic subset of reference slots that best matches this frame's
    # observed x-centers. This preserves an obscured gap: if L1 is missing, the
    # remaining three detections map to slots 2,3,4 instead of shifting to 1,2,3.
    from itertools import combinations

    best_slots: tuple[int, ...] | None = None
    best_cost: float | None = None
    for slots in combinations(range(4), len(ordered)):
        cost = sum(abs(observation[2] - reference_centers[slot]) for observation, slot in zip(ordered, slots, strict=False))
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_slots = slots
    if best_slots is None:
        return []
    return [(slot + 1, observation) for slot, observation in zip(best_slots, ordered, strict=False)]


def frame_ranked_lamp_observations(
    track_observations: dict[int, list[tuple]],
) -> dict[int, list[tuple]]:
    """Convert tracked observations into per-frame left-to-right lamp slots.

    ByteTrack identities are useful for smoothing a single detection path, but
    tiny distant PAPI lamps can swap track ids. User-facing frame analysis is
    inspected visually, so each frame must use the same convention as the overlay:
    Light 1..4 from image left-to-right. Missing lamps are kept as gaps whenever a
    four-lamp reference can be learned from the clip, so a dropped L1 does not make
    L2 temporarily become Light 1.
    """
    observations_by_frame: dict[int, list[tuple]] = {}
    for observations in track_observations.values():
        for observation in observations:
            if len(observation) < 4:
                continue
            observations_by_frame.setdefault(observation[0], []).append(observation)

    reference_centers = _reference_slot_centers(observations_by_frame)
    ranked: dict[int, list[tuple]] = {}
    for frame_index, observations in observations_by_frame.items():
        for lamp_index, observation in _assign_observations_to_slots(observations, reference_centers):
            _frame, state, center_x, confidence, *rest = observation
            ranked.setdefault(lamp_index, []).append(
                (frame_index, state, center_x, confidence, *rest)
            )

    return {lamp_index: sorted(obs, key=lambda item: item[0]) for lamp_index, obs in ranked.items()}


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
    stabilized_observations = denoise_track_observations(track_observations)
    if set(stabilized_observations).issubset({1, 2, 3, 4}):
        index_by_track = {track_id: track_id for track_id in stabilized_observations}
    else:
        index_by_track = lamp_index_by_track(stabilized_observations)

    def angle_at(frame_index: int) -> float | None:
        if frame_angles is not None and frame_index in frame_angles:
            return frame_angles[frame_index]
        return elevation_angle_deg

    events: list[TransitionEvent] = []
    for tid, obs in stabilized_observations.items():
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


# A transition-state run is reported only after it persists for multiple observed
# frames. The optional 3-class transition model is noisy around blend zones; a
# single isolated class-2 frame should not become a visible transition event.
MIN_TRANSITION_RUN_FRAMES = 2


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
    if set(track_observations).issubset({1, 2, 3, 4}):
        index_by_track = {track_id: track_id for track_id in track_observations}
    else:
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
        if from_state == to_state:
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


# Exact white-lamp count -> glidepath state for a complete 4-lamp PAPI unit. The white-count
# ORDERING is single-sourced from the offline decoder (papi.global_state.WHITE_COUNT_TO_CODE);
# only the API display vocabulary (the response contract) is backend-specific, so the two can
# no longer drift on which count means "too high" vs "too low".
_CODE_TO_API_STATE = {
    "4W": "far_too_high",       # 4 white
    "3W1R": "too_high",         # 3 white + 1 red
    "2W2R": "correct_glidepath",  # 2 white + 2 red
    "1W3R": "too_low",          # 1 white + 3 red
    "4R": "far_too_low",        # 4 red
}
_WHITE_COUNT_TO_STATE = {
    count: _CODE_TO_API_STATE[code] for count, code in WHITE_COUNT_TO_CODE.items()
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


def _expected_white_count_range(angle_deg: float) -> tuple[int, int]:
    """Min/max number of WHITE lamps a healthy PAPI shows at this viewing angle.

    A lamp is certainly white above set+halfwidth and certainly red below
    set-halfwidth; inside its blend zone it can read as either colour, so the
    range spans the blend-zone lamps.
    """
    certain_white = sum(
        1
        for set_angle in FAA_DEFAULT_SET_ANGLES_DEG
        if angle_deg > set_angle + TRANSITION_HALF_WIDTH_DEG
    )
    certain_red = sum(
        1
        for set_angle in FAA_DEFAULT_SET_ANGLES_DEG
        if angle_deg < set_angle - TRANSITION_HALF_WIDTH_DEG
    )
    return certain_white, len(FAA_DEFAULT_SET_ANGLES_DEG) - certain_red


def _is_contiguous_pattern(states: list[str]) -> bool:
    """True when the red/white sequence has at most one colour boundary."""
    return sum(1 for left, right in zip(states, states[1:], strict=False) if left != right) <= 1


def infer_single_missing_lamp_from_angle(
    lamps: list[LampResult],
    angle: AngleResult,
) -> list[LampResult]:
    """Infer one missing PAPI lamp's colour from the white-count geometry.

    The drone's elevation angle fixes HOW MANY of a healthy PAPI's four lamps
    show white (the set angles below it) — but WHICH image slot shows which
    colour is unknowable here: the left-to-right order flips with the approach
    direction (rwy 06 vs 24 view the same array from opposite sides), the EDNY
    transition data shows the per-slot binding reversed vs the config comment,
    and ``normalize_detections`` compacts 3 detections into slots 1..3 so the
    padded "missing" slot need not be the physically missing lamp. Counting
    sidesteps all three: the missing lamp is white exactly when the observed
    whites fall one short of the geometric white count.

    Conservative by design:
    * only runs when exactly one of the four slots is obscured/unknown,
    * requires an available, plausible angle,
    * skips when a blend-zone lamp makes both colours feasible,
    * skips when the observed colours already contradict the geometry — that
      mismatch can itself signal a real PAPI fault and must stay visible,
    * skips when the completed pattern could not be spatially contiguous
      (whites sit at one end of a healthy array; see the inline note on how
      interior vs last-slot gaps are treated).

    The inferred lamp is marked `inferred=True` and confidence 0.0 so users can
    see it was calculated from geometry, not detected by the model.
    """
    if not angle.angle_available or angle.elevation_angle_deg is None or not angle.plausible:
        return lamps

    # A "transition" lamp is a REAL 3-class-model detection, not an empty slot.
    # Without this guard it falls into ``missing`` below (it is outside
    # DETECTED_LAMP_STATES) and gets overwritten by a fabricated red/white —
    # destroying measured evidence. Geometry can't help here anyway: a lamp
    # mid-blend makes the white count genuinely ambiguous.
    if any(lamp.state == "transition" for lamp in lamps):
        return lamps

    detected = [lamp for lamp in lamps if lamp.state in DETECTED_LAMP_STATES]
    missing = [lamp for lamp in lamps if lamp.state not in DETECTED_LAMP_STATES]
    if len(detected) != 3 or len(missing) != 1:
        return lamps

    lowest, highest = _expected_white_count_range(angle.elevation_angle_deg)
    observed_whites = sum(1 for lamp in detected if lamp.state == "white")
    feasible = {
        state
        for state, white_total in (("white", observed_whites + 1), ("red", observed_whites))
        if lowest <= white_total <= highest
    }
    if len(feasible) != 1:
        return lamps

    missing_lamp = missing[0]
    inferred_state = feasible.pop()

    # Spatial sanity: a healthy PAPI's whites are contiguous at one end, so the
    # completed pattern may have at most one red/white boundary. An INTERIOR
    # missing slot sits between observed lamps, so its position is meaningful
    # and the inferred colour must fit exactly there. A missing LAST slot is
    # indistinguishable from normalize_detections' compaction padding (the
    # physically missing lamp could be anywhere), so it only requires SOME
    # insertion position to yield a contiguous pattern.
    observed_states = [
        lamp.state for lamp in sorted(detected, key=lambda lamp: lamp.index)
    ]
    interior = any(lamp.index > missing_lamp.index for lamp in detected)
    if interior:
        positions = [sum(1 for lamp in detected if lamp.index < missing_lamp.index)]
    else:
        positions = range(len(observed_states) + 1)
    if not any(
        _is_contiguous_pattern(
            observed_states[:position] + [inferred_state] + observed_states[position:]
        )
        for position in positions
    ):
        return lamps

    inferred = LampResult(
        index=missing_lamp.index,
        state=inferred_state,
        confidence=0.0,
        bbox=None,
        inferred=True,
        inference_note=(
            "Inferred from the drone elevation angle and the standard PAPI set-angle "
            "model because this lamp was not detected by the AI."
        ),
    )
    return [inferred if lamp is missing_lamp else lamp.model_copy(deep=True) for lamp in lamps]


def confidence_from_lamps(lamps: list[LampResult]) -> float:
    """Mean detector confidence over the lamps that were actually detected.

    Only red/white lamps (``DETECTED_LAMP_STATES``) carry a real measurement;
    "obscured"/"unknown" slots have no detection behind them, so averaging them in
    would dilute the score toward zero. Returns 0.0 when nothing was detected.
    """
    detected = [
        lamp.confidence
        for lamp in lamps
        if lamp.state in DETECTED_LAMP_STATES and not lamp.inferred
    ]
    if not detected:
        return 0.0
    return round(sum(detected) / len(detected), 4)
