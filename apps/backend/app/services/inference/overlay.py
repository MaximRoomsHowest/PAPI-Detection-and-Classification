"""Annotated-frame drawing: lamp boxes + a verdict/confidence/angle banner."""

from typing import Any

from app.validation.schemas import LampResult

# BGR color map (cv2 stores BGR, not RGB). At runtime a lamp's per-frame state
# is only red/white/unknown (the detector is two-class), so the overlay draws
# those; white<->red transitions are reported as temporal events
# (detect_lamp_transitions), not per-frame. The amber 'transition' entry is
# retained so the overlay is ready should a per-frame transition state be added.
LAMP_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (245, 245, 245),
    "red": (0, 0, 255),
    "transition": (0, 165, 255),
    "obscured": (90, 90, 90),
    "unknown": (128, 128, 128),
}


def draw_overlay(
    cv2: Any,
    frame: Any,
    lamps: list[LampResult],
    global_state: str,
    confidence: float,
    elevation_angle_deg: float | None,
) -> Any:
    """Draw per-lamp boxes/labels and the summary banner onto ``frame`` in place.

    Returns the same frame the caller passed in (mutated), so it can be written
    straight to the video writer or the annotated-image artifact.
    """
    for lamp in lamps:
        if lamp.bbox is None:
            continue
        color = LAMP_COLORS.get(lamp.state, LAMP_COLORS["unknown"])
        cv2.rectangle(frame, (lamp.bbox.x1, lamp.bbox.y1), (lamp.bbox.x2, lamp.bbox.y2), color, 2)
        cv2.putText(
            frame,
            f"L{lamp.index}: {lamp.state} {lamp.confidence:.2f}",
            (lamp.bbox.x1, max(24, lamp.bbox.y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )

    angle_text = "angle: unavailable" if elevation_angle_deg is None else f"angle: {elevation_angle_deg:.3f} deg"
    lines = [
        f"PAPI: {global_state}",
        f"confidence: {confidence:.2f}",
        angle_text,
    ]
    y = 40
    for line in lines:
        cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
        y += 36
    return frame
