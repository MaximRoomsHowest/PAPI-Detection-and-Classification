from app.services.state import confidence_from_lamps, global_state_from_lamps, normalize_detections
from app.validation.schemas import AnglePerLight


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


def test_per_lamp_transition_promoted_when_elevation_near_set_angle():
    """Audit B-CRIT-1: when |elevation - set_angle| <= half_width, the
    YOLO color verdict is overridden to "transition". This is how the
    backend satisfies the client requirement "label each lamp white,
    red, or transition" without needing a third detector class."""
    # YOLO sees four white lamps; geometry says lamp 1 is in its transition band.
    detections = [
        {"class_id": 1, "confidence": 0.95, "bbox": {"x1": 100, "y1": 20, "x2": 130, "y2": 50}},
        {"class_id": 1, "confidence": 0.94, "bbox": {"x1": 200, "y1": 20, "x2": 230, "y2": 50}},
        {"class_id": 1, "confidence": 0.93, "bbox": {"x1": 300, "y1": 20, "x2": 330, "y2": 50}},
        {"class_id": 1, "confidence": 0.92, "bbox": {"x1": 400, "y1": 20, "x2": 430, "y2": 50}},
    ]
    # Lamp 1's FAA default set-angle is 2.50 deg; place the drone exactly there
    # so |elev - set| = 0 < 0.10 half-width -> transition.
    per_light_angles = [
        AnglePerLight(runway_lamp=1, distance_m=500.0, elevation_angle_deg=2.50),
        AnglePerLight(runway_lamp=2, distance_m=500.0, elevation_angle_deg=3.00),
        AnglePerLight(runway_lamp=3, distance_m=500.0, elevation_angle_deg=3.50),
        AnglePerLight(runway_lamp=4, distance_m=500.0, elevation_angle_deg=4.00),
    ]
    lamps = normalize_detections(detections, per_light_angles=per_light_angles)

    assert lamps[0].state == "transition"
    assert lamps[1].state == "white"  # far above its set-angle
    assert lamps[2].state == "white"  # at its set-angle is also fine
    assert lamps[3].state == "white"


def test_global_state_becomes_transition_when_any_lamp_in_transition():
    """Audit B-CRIT-1 follow-on: any lamp in transition shadows the
    five nominal global states. Matches papi.global_state semantics."""
    detections = [
        {"class_id": 1, "confidence": 0.9, "bbox": {"x1": 100, "y1": 20, "x2": 130, "y2": 50}},
        {"class_id": 1, "confidence": 0.9, "bbox": {"x1": 200, "y1": 20, "x2": 230, "y2": 50}},
        {"class_id": 0, "confidence": 0.9, "bbox": {"x1": 300, "y1": 20, "x2": 330, "y2": 50}},
        {"class_id": 0, "confidence": 0.9, "bbox": {"x1": 400, "y1": 20, "x2": 430, "y2": 50}},
    ]
    # Lamp 2 in its transition band; others outside.
    per_light_angles = [
        AnglePerLight(runway_lamp=1, distance_m=500.0, elevation_angle_deg=4.00),
        AnglePerLight(runway_lamp=2, distance_m=500.0, elevation_angle_deg=2.83),  # set-angle
        AnglePerLight(runway_lamp=3, distance_m=500.0, elevation_angle_deg=2.50),
        AnglePerLight(runway_lamp=4, distance_m=500.0, elevation_angle_deg=2.50),
    ]
    lamps = normalize_detections(detections, per_light_angles=per_light_angles)

    assert lamps[1].state == "transition"
    assert global_state_from_lamps(lamps) == "transition"


def test_without_angles_state_falls_back_to_color_only():
    """No drone metadata? The system still works -- we just lose the
    transition signal and report white/red as before."""
    detections = [
        {"class_id": 1, "confidence": 0.95, "bbox": {"x1": 100, "y1": 20, "x2": 130, "y2": 50}},
        {"class_id": 0, "confidence": 0.95, "bbox": {"x1": 200, "y1": 20, "x2": 230, "y2": 50}},
        {"class_id": 0, "confidence": 0.95, "bbox": {"x1": 300, "y1": 20, "x2": 330, "y2": 50}},
        {"class_id": 0, "confidence": 0.95, "bbox": {"x1": 400, "y1": 20, "x2": 430, "y2": 50}},
    ]
    lamps = normalize_detections(detections)  # no per_light_angles

    assert [lamp.state for lamp in lamps] == ["white", "red", "red", "red"]
    assert global_state_from_lamps(lamps) == "too_low"
