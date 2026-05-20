from app.services.state import confidence_from_lamps, global_state_from_lamps, normalize_detections


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

