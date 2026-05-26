from collections import Counter

from app.validation.schemas import BoundingBox, LampResult

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
    "unknown": "Unknown",
}


def normalize_detections(raw_detections: list[dict]) -> list[LampResult]:
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


def global_state_from_lamps(lamps: list[LampResult]) -> str:
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
