"""Per-lamp + global state derivation for the backend API.

Detection-class IDs from the YOLO model are 0=red, 1=white. The client brief
also requires a third per-lamp label, "transition", when a lamp is in the
narrow angular blend zone (~set_angle ± transition_half_width). That third
state is geometry-derived rather than learned by YOLO -- it lives in
``packages/papi/src/papi/lamp_state.py``. This module wires the geometric
verdict back into per-lamp results so the API actually emits "transition"
when conditions are met (audit B-CRIT-1).
"""

from collections import Counter

from app.validation.schemas import AnglePerLight, BoundingBox, LampResult

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

# FAA defaults (deg). Matches configs/papi_edny.yaml when the YAML has nulls.
# Innermost (lamp 1) -> outermost (lamp 4); the innermost has the lowest
# set-angle and turns red first when the pilot sinks below the path.
FAA_DEFAULT_SET_ANGLES_DEG: tuple[float, float, float, float] = (2.50, 2.83, 3.17, 3.50)
DEFAULT_TRANSITION_HALF_WIDTH_DEG: float = 0.10


def _maybe_transition_state(
    color_state: str,
    elevation_deg: float | None,
    set_angle_deg: float,
    half_width_deg: float,
) -> str:
    """Promote 'red'/'white' to 'transition' when |elevation - set_angle| <= half_width.

    If the elevation angle isn't available (e.g., no drone GPS metadata),
    leave the YOLO-derived color state unchanged.
    """
    if elevation_deg is None:
        return color_state
    if abs(elevation_deg - set_angle_deg) <= half_width_deg:
        return "transition"
    return color_state


def normalize_detections(
    raw_detections: list[dict],
    per_light_angles: list[AnglePerLight] | None = None,
    set_angles_deg: tuple[float, float, float, float] = FAA_DEFAULT_SET_ANGLES_DEG,
    transition_half_width_deg: float = DEFAULT_TRANSITION_HALF_WIDTH_DEG,
) -> list[LampResult]:
    """Build per-lamp results sorted left-to-right.

    When ``per_light_angles`` is provided (i.e., the request supplied drone
    GPS/altitude or the EXIF contained it), each lamp's color verdict is
    promoted to 'transition' if its elevation angle sits inside the
    set_angle +/- half_width band. This satisfies the client requirement
    "label each lamp white / red / transition" (audit B-CRIT-1).
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

    # Look-up table: lamp index (1..4) -> elevation angle in deg (or None).
    angle_by_lamp: dict[int, float | None] = {}
    if per_light_angles:
        for entry in per_light_angles:
            angle_by_lamp[int(entry.runway_lamp)] = float(entry.elevation_angle_deg)

    lamps: list[LampResult] = []
    for index, (_, confidence, state, bbox) in enumerate(candidates, start=1):
        # Lamp's set-angle indexed 0..3 even though point numbers are 1..4.
        set_angle = set_angles_deg[index - 1]
        promoted = _maybe_transition_state(
            color_state=state,
            elevation_deg=angle_by_lamp.get(index),
            set_angle_deg=set_angle,
            half_width_deg=transition_half_width_deg,
        )
        lamps.append(
            LampResult(
                index=index,
                state=promoted,
                confidence=confidence,
                bbox=BoundingBox(**bbox),
            )
        )

    while len(lamps) < 4:
        lamps.append(LampResult(index=len(lamps) + 1, state="unknown", confidence=0.0))

    return lamps


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
