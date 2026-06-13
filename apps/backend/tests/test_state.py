from app.services.state import (
    aggregate_transition_state_events,
    bind_lamps_to_runway_display,
    bind_transitions_to_runway_display,
    confidence_from_lamps,
    detect_lamp_transitions,
    frame_ranked_lamp_observations,
    global_state_from_lamps,
    infer_single_missing_lamp_from_angle,
    normalize_detections,
    transition_events_from_state_runs,
)
from app.validation.schemas import AngleResult, LampResult, TransitionEvent


def test_normalize_detections_sorts_lamps_left_to_right():
    detections = [
        {"class_id": 0, "confidence": 0.8, "bbox": {"x1": 300, "y1": 20, "x2": 330, "y2": 50}},
        {"class_id": 1, "confidence": 0.9, "bbox": {"x1": 100, "y1": 20, "x2": 130, "y2": 50}},
        {"class_id": 0, "confidence": 0.7, "bbox": {"x1": 400, "y1": 20, "x2": 430, "y2": 50}},
        {"class_id": 1, "confidence": 0.95, "bbox": {"x1": 200, "y1": 20, "x2": 230, "y2": 50}},
    ]

    lamps = normalize_detections(detections)

    assert [lamp.index for lamp in lamps] == [1, 2, 3, 4]
    assert [lamp.state for lamp in lamps] == ["white", "white", "red", "red"]


def test_display_binding_keeps_left_to_right_lamp_order_for_rwy24():
    lamps = [
        LampResult(index=1, state="red", confidence=0.8),
        LampResult(index=2, state="white", confidence=0.7),
        LampResult(index=3, state="red", confidence=0.6),
        LampResult(index=4, state="white", confidence=0.9),
    ]

    bound = bind_lamps_to_runway_display(lamps, "papi_24")

    assert [lamp.index for lamp in bound] == [1, 2, 3, 4]
    assert [lamp.state for lamp in bound] == ["red", "white", "red", "white"]
    assert [lamp.index for lamp in lamps] == [1, 2, 3, 4]


def test_rwy06_display_binding_keeps_lamp_order():
    lamps = [
        LampResult(index=1, state="red", confidence=0.8),
        LampResult(index=4, state="white", confidence=0.9),
    ]

    bound = bind_lamps_to_runway_display(lamps, "papi_06")

    assert [(lamp.index, lamp.state) for lamp in bound] == [(1, "red"), (4, "white")]


def test_display_binding_keeps_left_to_right_transition_lamp_indices_for_rwy24():
    events = [
        TransitionEvent(lamp_index=1, from_state="red", to_state="white", frame_index=32),
        TransitionEvent(lamp_index=4, from_state="white", to_state="red", frame_index=31),
    ]

    bound = bind_transitions_to_runway_display(events, "papi_24")

    assert [(event.lamp_index, event.frame_index) for event in bound] == [(4, 31), (1, 32)]


def test_normalize_detections_keeps_top_four_by_confidence_then_resorts_by_x():
    """Five detections: the four HIGHEST-CONFIDENCE survive, then re-sort by x.

    This pins the current selection strategy — including its known limitation:
    a high-confidence false positive displaces the lowest-confidence REAL lamp
    (audit 2026-06-11 near-miss). If selection ever becomes cluster-aware this
    test should be updated deliberately, not silently.
    """
    detections = [
        {"class_id": 1, "confidence": 0.90, "bbox": {"x1": 100, "y1": 20, "x2": 130, "y2": 50}},
        {"class_id": 1, "confidence": 0.91, "bbox": {"x1": 200, "y1": 20, "x2": 230, "y2": 50}},
        # High-confidence interloper between lamps 2 and 3.
        {"class_id": 0, "confidence": 0.95, "bbox": {"x1": 250, "y1": 20, "x2": 280, "y2": 50}},
        {"class_id": 0, "confidence": 0.89, "bbox": {"x1": 300, "y1": 20, "x2": 330, "y2": 50}},
        # The real fourth lamp loses the confidence cut.
        {"class_id": 0, "confidence": 0.60, "bbox": {"x1": 400, "y1": 20, "x2": 430, "y2": 50}},
    ]

    lamps = normalize_detections(detections)

    assert [lamp.index for lamp in lamps] == [1, 2, 3, 4]
    # x-order of the four survivors: 100, 200, 250 (interloper), 300 — the real
    # lamp at x=400 (conf 0.60) was dropped by the confidence cut.
    assert [lamp.state for lamp in lamps] == ["white", "white", "red", "red"]
    assert [lamp.confidence for lamp in lamps] == [0.90, 0.91, 0.95, 0.89]


def test_global_state_mapping_uses_papi_ratios():
    assert global_state_from_lamps(normalize_detections([])) == "unknown"
    assert _state_for_classes([0]) == "unknown"
    assert _state_for_classes([1, 1, 1, 1]) == "far_too_high"
    assert _state_for_classes([1, 1, 1, 0]) == "too_high"
    assert _state_for_classes([1, 1, 0, 0]) == "correct_glidepath"
    assert _state_for_classes([1, 0, 0, 0]) == "too_low"
    assert _state_for_classes([0, 0, 0, 0]) == "far_too_low"


def test_confidence_ignores_unknown_lamps():
    lamps = normalize_detections(
        [
            {"class_id": 1, "confidence": 0.8, "bbox": {"x1": 1, "y1": 1, "x2": 2, "y2": 2}},
            {"class_id": 0, "confidence": 0.6, "bbox": {"x1": 3, "y1": 1, "x2": 4, "y2": 2}},
        ]
    )

    assert confidence_from_lamps(lamps) == 0.7


def test_confidence_ignores_inferred_lamps():
    lamps = [
        LampResult(index=1, state="red", confidence=0.8),
        LampResult(index=2, state="red", confidence=0.6),
        LampResult(index=3, state="white", confidence=0.7),
        LampResult(index=4, state="white", confidence=0.0, inferred=True),
    ]

    assert confidence_from_lamps(lamps) == 0.7


def test_normalize_pads_missing_lamps_as_obscured():
    """Fewer than 4 detections -> the empty slots are 'obscured' (a real, charted
    category for 'detector found nothing here'), not the generic 'unknown'."""
    lamps = normalize_detections(
        [{"class_id": 1, "confidence": 0.9, "bbox": {"x1": 1, "y1": 1, "x2": 2, "y2": 2}}]
    )
    assert [lamp.state for lamp in lamps] == ["white", "obscured", "obscured", "obscured"]
    # Global verdict is still 'unknown' when <4 lamps are red/white (no logic change).
    assert global_state_from_lamps(lamps) == "unknown"
    # Obscured slots carry no detection, so confidence reflects only the white lamp.
    assert confidence_from_lamps(lamps) == 0.9


def _three_lamps_red_red_white():
    """Two reds + one white via normalize_detections: slots 1..3 + slot 4 obscured."""
    return normalize_detections(
        [
            {"class_id": 0, "confidence": 0.9, "bbox": {"x1": 10, "y1": 1, "x2": 12, "y2": 3}},
            {"class_id": 0, "confidence": 0.8, "bbox": {"x1": 20, "y1": 1, "x2": 22, "y2": 3}},
            {"class_id": 1, "confidence": 0.7, "bbox": {"x1": 30, "y1": 1, "x2": 32, "y2": 3}},
        ]
    )


def _angle(deg):
    return AngleResult(
        angle_available=True,
        elevation_angle_deg=deg,
        angle_source="test",
        angle_note="test",
    )


def test_infers_one_missing_lamp_from_angle():
    """On-slope (3.0 deg) the geometry expects exactly 2 whites; with R,R,W
    observed the missing lamp must be the second white — regardless of which
    side of the array carries the low set angles. The EDNY rwy-24 data has the
    image order reversed vs the config-comment convention, so a slot-indexed
    set-angle lookup would get exactly this shape wrong."""
    lamps = _three_lamps_red_red_white()

    inferred = infer_single_missing_lamp_from_angle(lamps, _angle(3.0))

    assert [lamp.state for lamp in inferred] == ["red", "red", "white", "white"]
    assert inferred[3].inferred is True
    assert inferred[3].confidence == 0.0
    assert inferred[3].bbox is None
    assert inferred[3].inference_note
    assert global_state_from_lamps(inferred) == "correct_glidepath"


def test_infers_red_for_an_interior_slot_by_identity():
    """A video aggregate can leave an INTERIOR slot undetected; the inferred
    lamp must replace that exact slot (matched by identity, not position
    arithmetic) and the completed pattern stays contiguous."""
    lamps = [
        LampResult(index=1, state="white", confidence=0.9),
        LampResult(index=2, state="white", confidence=0.8),
        LampResult(index=3, state="obscured", confidence=0.0),
        LampResult(index=4, state="red", confidence=0.7),
    ]

    inferred = infer_single_missing_lamp_from_angle(lamps, _angle(3.0))

    assert [lamp.state for lamp in inferred] == ["white", "white", "red", "red"]
    assert inferred[2].inferred is True
    assert inferred[2].index == 3


def test_does_not_infer_missing_lamp_without_angle_or_near_transition():
    lamps = _three_lamps_red_red_white()
    missing_angle = AngleResult(angle_available=False, angle_note="no metadata")
    # 3.17 deg sits in that lamp's blend zone: 2 or 3 whites are both feasible,
    # so the missing lamp's colour is genuinely ambiguous.
    boundary_lamps = [
        LampResult(index=1, state="white", confidence=0.9),
        LampResult(index=2, state="white", confidence=0.8),
        LampResult(index=3, state="red", confidence=0.7),
        LampResult(index=4, state="obscured", confidence=0.0),
    ]

    assert infer_single_missing_lamp_from_angle(lamps, missing_angle) == lamps
    assert infer_single_missing_lamp_from_angle(boundary_lamps, _angle(3.17)) == boundary_lamps


def test_does_not_infer_over_a_real_transition_detection():
    """A 3-class model's "transition" lamp is a REAL detection, not an empty
    slot. It sits outside DETECTED_LAMP_STATES, so without an explicit guard it
    is treated as the missing lamp and overwritten with a fabricated red/white
    — destroying measured evidence (audit 2026-06-12)."""
    lamps = [
        LampResult(index=1, state="red", confidence=0.9),
        LampResult(index=2, state="red", confidence=0.8),
        LampResult(index=3, state="transition", confidence=0.7),
        LampResult(index=4, state="white", confidence=0.7),
    ]

    result = infer_single_missing_lamp_from_angle(lamps, _angle(3.0))

    assert result == lamps
    assert result[2].state == "transition"
    assert not any(lamp.inferred for lamp in result)


def test_does_not_infer_when_observations_contradict_geometry():
    """Well above every set angle (3.8 deg) a healthy PAPI shows 4 whites;
    observing two reds means the array (or the angle) is wrong — never paper
    over that with a fabricated state. The slot-indexed approach happily
    'inferred' a lamp for exactly this shape."""
    lamps = _three_lamps_red_red_white()

    assert infer_single_missing_lamp_from_angle(lamps, _angle(3.8)) == lamps


def test_does_not_infer_a_spatially_impossible_pattern():
    """Counts alone can be satisfiable while the completed pattern is not:
    W ? W R would put the inferred red between two whites, which a healthy
    PAPI cannot show (whites sit contiguously at one end)."""
    lamps = [
        LampResult(index=1, state="white", confidence=0.9),
        LampResult(index=2, state="obscured", confidence=0.0),
        LampResult(index=3, state="white", confidence=0.8),
        LampResult(index=4, state="red", confidence=0.7),
    ]

    assert infer_single_missing_lamp_from_angle(lamps, _angle(3.0)) == lamps


def test_infers_white_when_blend_zone_red_explains_the_observation():
    """3.45 deg: three set angles are certainly below (white) and the 3.50 lamp
    is in its blend zone. Observing W,W,R leaves only 'white' feasible for the
    missing slot — the observed red is explained by the blend-zone lamp."""
    lamps = [
        LampResult(index=1, state="white", confidence=0.9),
        LampResult(index=2, state="white", confidence=0.8),
        LampResult(index=3, state="red", confidence=0.7),
        LampResult(index=4, state="obscured", confidence=0.0),
    ]

    inferred = infer_single_missing_lamp_from_angle(lamps, _angle(3.45))

    assert [lamp.state for lamp in inferred] == ["white", "white", "red", "white"]
    assert inferred[3].inferred is True


def test_does_not_infer_with_more_than_one_missing_lamp():
    lamps = [
        LampResult(index=1, state="red", confidence=0.9),
        LampResult(index=2, state="red", confidence=0.8),
        LampResult(index=3, state="obscured", confidence=0.0),
        LampResult(index=4, state="obscured", confidence=0.0),
    ]

    assert infer_single_missing_lamp_from_angle(lamps, _angle(3.0)) == lamps


def test_single_frame_states_are_colour_only():
    """A single frame is never 'transition' -- only red / white / unknown.
    A transition is a temporal red<->white event detected across frames."""
    detections = [
        {"class_id": 1, "confidence": 0.95, "bbox": {"x1": 100, "y1": 20, "x2": 130, "y2": 50}},
        {"class_id": 0, "confidence": 0.95, "bbox": {"x1": 200, "y1": 20, "x2": 230, "y2": 50}},
        {"class_id": 0, "confidence": 0.95, "bbox": {"x1": 300, "y1": 20, "x2": 330, "y2": 50}},
        {"class_id": 0, "confidence": 0.95, "bbox": {"x1": 400, "y1": 20, "x2": 430, "y2": 50}},
    ]
    lamps = normalize_detections(detections)

    assert [lamp.state for lamp in lamps] == ["white", "red", "red", "red"]
    assert global_state_from_lamps(lamps) == "too_low"
    assert all(lamp.state != "transition" for lamp in lamps)


def test_global_state_is_transition_when_a_lamp_is_transition():
    """global_state_from_lamps still shadows the five verdicts when a lamp is in
    transition (kept for schema/aggregate compatibility)."""
    lamps = [
        LampResult(index=1, state="white", confidence=0.9),
        LampResult(index=2, state="transition", confidence=0.9),
        LampResult(index=3, state="red", confidence=0.9),
        LampResult(index=4, state="red", confidence=0.9),
    ]
    assert global_state_from_lamps(lamps) == "transition"


def _state_for_classes(classes):
    detections = [
        {
            "class_id": class_id,
            "confidence": 0.9,
            "bbox": {"x1": index * 10, "y1": 0, "x2": index * 10 + 5, "y2": 5},
        }
        for index, class_id in enumerate(classes)
    ]
    return global_state_from_lamps(normalize_detections(detections))


def test_detect_lamp_transitions_finds_consecutive_red_to_white():
    """A tracked lamp that switches red->white between consecutive frames emits one
    event, numbered by left-to-right position and carrying the associated angle."""
    track_observations = {
        7: [(0, "red", 100.0), (1, "red", 100.0), (2, "white", 100.0)],  # leftmost
        9: [(0, "white", 300.0), (1, "white", 300.0), (2, "white", 300.0)],
    }
    events = detect_lamp_transitions(track_observations, elevation_angle_deg=3.05)

    assert len(events) == 1
    event = events[0]
    assert event.lamp_index == 1
    assert (event.from_state, event.to_state) == ("red", "white")
    assert event.frame_index == 2
    assert event.elevation_angle_deg == 3.05


def test_frame_ranked_lamp_observations_follow_left_to_right_each_frame():
    observations = {
        10: [(0, "red", 100.0, 0.9), (1, "white", 400.0, 0.9)],
        20: [(0, "white", 400.0, 0.9), (1, "red", 100.0, 0.9)],
    }

    ranked = frame_ranked_lamp_observations(observations)

    assert [obs[1] for obs in ranked[1]] == ["red", "red"]
    assert [obs[1] for obs in ranked[2]] == ["white", "white"]


def test_frame_ranked_lamp_observations_preserve_missing_slot_gaps():
    """A dropped left lamp must not make the remaining lamps shift into lower slots."""

    def obs(frame: int, state: str, x: float) -> tuple:
        return (frame, state, x, 0.9)

    observations = {
        101: [obs(0, "red", 10.0), obs(3, "red", 10.0)],
        102: [obs(0, "red", 20.0), obs(1, "white", 20.0), obs(2, "white", 20.0), obs(3, "white", 20.0)],
        103: [obs(0, "red", 30.0), obs(1, "red", 30.0), obs(2, "red", 30.0), obs(3, "red", 30.0)],
        104: [obs(0, "red", 40.0), obs(1, "red", 40.0), obs(2, "red", 40.0), obs(3, "red", 40.0)],
    }

    ranked = frame_ranked_lamp_observations(observations)
    events = detect_lamp_transitions(ranked)

    assert [entry[0] for entry in ranked[1]] == [0, 3]
    assert [entry[1] for entry in ranked[1]] == ["red", "red"]
    assert [(event.lamp_index, event.from_state, event.to_state, event.frame_index) for event in events] == [
        (2, "red", "white", 1)
    ]


def test_detect_lamp_transitions_ignores_large_frame_gap():
    """A switch across a gap larger than TRANSITION_MAX_FRAME_GAP is not counted."""
    track_observations = {3: [(0, "red", 50.0), (5, "white", 50.0)]}  # gap 5 > 2
    assert detect_lamp_transitions(track_observations) == []


def test_detect_lamp_transitions_gap_tolerance_boundary():
    """Gap tolerance (TRANSITION_MAX_FRAME_GAP=2): a 2-frame gap is still counted so
    a single dropped/occluded frame can't silently drop a real switch; a 3-frame
    gap is rejected. Pins the recently-landed boundary (audit H4)."""
    # gap 2 -> exactly one event, attributed to the later frame
    events = detect_lamp_transitions({1: [(0, "red", 10.0), (2, "white", 10.0)]})
    assert len(events) == 1
    assert events[0].lamp_index == 1
    assert (events[0].from_state, events[0].to_state) == ("red", "white")
    assert events[0].frame_index == 2
    # gap 3 -> rejected (exceeds the tolerance)
    assert detect_lamp_transitions({1: [(0, "red", 10.0), (3, "white", 10.0)]}) == []


def test_detect_lamp_transitions_empty_without_a_switch():
    assert detect_lamp_transitions({}) == []
    assert detect_lamp_transitions({1: [(0, "red", 10.0)]}) == []  # single observation


def test_detect_lamp_transitions_suppresses_single_frame_colour_blips():
    """A stable lamp can briefly misclassify for one frame; that should not emit
    two false transition events around the real sustained crossing."""
    observations = {
        1: [
            (26, "red", 10.0),
            (27, "red", 10.0),
            (28, "white", 10.0),  # isolated white blip
            (29, "red", 10.0),
            (30, "red", 10.0),
            (31, "red", 10.0),
            (32, "white", 10.0),  # sustained red -> white crossing
            (33, "white", 10.0),
            (47, "white", 10.0),
            (48, "red", 10.0),  # isolated red blip
            (49, "white", 10.0),
            (50, "white", 10.0),
        ]
    }

    events = detect_lamp_transitions(observations)

    assert [(event.from_state, event.to_state, event.frame_index) for event in events] == [
        ("red", "white", 32)
    ]


def test_aggregate_transition_state_events_groups_a_run():
    """A 3-class model reads 'transition' for a run of frames; the run collapses to one event
    with a stable id, frame span, duration, and the bracketing red/white states + angles."""
    obs = {5: [(0, "red", 100.0), (1, "transition", 100.0), (2, "transition", 100.0), (3, "white", 100.0)]}
    events = aggregate_transition_state_events(obs, frame_angles={1: 3.10, 2: 3.05})
    assert len(events) == 1
    e = events[0]
    assert e["transition_event_id"] == "L1-E1"
    assert e["lamp_index"] == 1
    assert (e["start_frame"], e["end_frame"], e["duration_frames"]) == (1, 2, 2)
    assert (e["from_state"], e["to_state"]) == ("red", "white")
    assert (e["start_angle_deg"], e["end_angle_deg"]) == (3.10, 3.05)


def test_aggregate_transition_state_events_empty_for_two_class():
    """A 2-class model never emits 'transition', so no state-run events are produced."""
    assert aggregate_transition_state_events({5: [(0, "red", 1.0), (1, "white", 1.0)]}) == []


def test_aggregate_transition_state_events_min_run_filters_flicker():
    """A single isolated 'transition' frame is dropped by the model-method default."""
    obs = {5: [(0, "red", 1.0), (1, "transition", 1.0), (2, "red", 1.0)]}
    assert aggregate_transition_state_events(obs) == []
    assert len(aggregate_transition_state_events(obs, min_run_frames=1)) == 1


def test_transition_events_from_state_runs_is_the_model_method():
    """The 'model' method emits one TransitionEvent per complete class-2 run, carrying the run's
    span/duration, method='model', the bracketing red/white states, and the start-frame angle."""
    obs = {5: [(0, "red", 100.0), (1, "transition", 100.0), (2, "transition", 100.0), (3, "white", 100.0)]}
    events = transition_events_from_state_runs(obs, frame_angles={1: 3.10})
    assert len(events) == 1
    e = events[0]
    assert e.method == "model"
    assert (e.from_state, e.to_state) == ("red", "white")
    assert (e.frame_index, e.start_frame, e.end_frame, e.duration_frames) == (1, 1, 2, 2)
    assert e.transition_event_id == "L1-E1"
    assert e.elevation_angle_deg == 3.10


def test_transition_events_from_state_runs_empty_for_two_class():
    """A 2-class model never emits 'transition' states -> the model method yields no events."""
    assert transition_events_from_state_runs({5: [(0, "red", 1.0), (1, "white", 1.0)]}) == []


def test_transition_events_from_state_runs_skips_incomplete_run():
    """A run with no stable colour after it (track ends mid-transition) is skipped so to_state
    never becomes None."""
    assert transition_events_from_state_runs({5: [(0, "red", 1.0), (1, "transition", 1.0)]}) == []


def test_transition_events_from_state_runs_skips_non_colour_change_runs():
    """A model class-2 run bracketed by the same colour is flicker, not a red/white transition."""
    obs = {
        5: [
            (0, "red", 100.0),
            (1, "transition", 100.0),
            (2, "transition", 100.0),
            (3, "red", 100.0),
        ]
    }

    assert transition_events_from_state_runs(obs, frame_angles={1: 3.10}) == []
