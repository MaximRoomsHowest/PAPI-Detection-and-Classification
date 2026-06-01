from app.services.state import (
    confidence_from_lamps,
    detect_lamp_transitions,
    global_state_from_lamps,
    normalize_detections,
)
from app.validation.schemas import LampResult


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
