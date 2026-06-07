from typing import Literal

from pydantic import BaseModel, Field

from app.validation.schemas.common import GlobalState
from app.validation.schemas.lamp import FrameLampState


class AnglePerLight(BaseModel):
    """Per-lamp geometry: horizontal ground distance and elevation angle to one lamp.

    ``distance_m`` is a horizontal distance (``math.hypot`` of the ENU east/north
    components) and is therefore never negative.
    """

    runway_lamp: int
    distance_m: float = Field(ge=0.0)
    elevation_angle_deg: float


class AngleResult(BaseModel):
    angle_available: bool
    elevation_angle_deg: float | None = None
    per_light_angles: list[AnglePerLight] = Field(default_factory=list)
    angle_source: str | None = None
    angle_note: str
    # Sanity check on the runway<->metadata relationship: the angle is always
    # geometrically computable, but if the drone fix is implausibly far from the
    # selected runway's nearest lamp it almost certainly means the wrong runway was
    # chosen (or the coordinates are in a different datum). ``plausible`` stays True
    # for every existing path (incl. the not-available one — no geometry to judge),
    # so the field is purely additive; the angle is NEVER withheld, only flagged.
    plausible: bool = True
    plausibility_note: str | None = None
    # Horizontal ground distance to the closest lamp (m). Surfaced so the UI can
    # show "how far the drone was" and back the plausibility flag with a number.
    nearest_lamp_distance_m: float | None = None
    # First-order 1-sigma uncertainty (deg) on the midpoint elevation angle,
    # propagated from the DJI RTK reported standard deviations (RtkStdLat/Lon/Hgt);
    # surveyed lamp coordinates are treated as exact. Only set when the fix carries
    # RTK std (the embedded-XMP path) — None elsewhere, so no fabricated confidence.
    elevation_angle_uncertainty_deg: float | None = None


class TransitionEvent(BaseModel):
    """A temporal red<->white change on one tracked PAPI lamp.

    Per the project design (docs/label_spec.md), a "transition" is an event
    observed by tracking a lamp across consecutive video frames -- not a
    per-frame geometric verdict. ``elevation_angle_deg`` is the viewing angle
    associated with the event (one value per uploaded video; None when no drone
    telemetry was supplied).
    """

    lamp_index: int
    from_state: Literal["red", "white"]
    to_state: Literal["red", "white"]
    frame_index: int
    elevation_angle_deg: float | None = None
    # Which method produced this event: "tracking" (temporal red<->white flip on the 2-class
    # model) or "model" (a learned class-2 transition-state run from the 3-class detector).
    # Additive — existing tracking events keep the default.
    method: Literal["tracking", "model"] = "tracking"
    # Span fields populated by the "model" method (a transition state persists for a run of
    # frames); None for the single-frame "tracking" flip. ``frame_index`` is the run start.
    transition_event_id: str | None = None
    start_frame: int | None = None
    end_frame: int | None = None
    duration_frames: int | None = None


class FramePoint(BaseModel):
    """One sample in a video's per-frame confidence/verdict series.

    ``confidence`` is the raw per-frame detection confidence (a probability) and
    ``state`` the per-frame global verdict, both computed for every frame inside
    the tracked-sequence loop. They are the inputs to the sliding-window smoothing
    used for the annotated overlay; surfaced here so the UI can draw a real
    frame-by-frame confidence curve instead of only the single aggregate score.
    """

    frame_index: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    state: GlobalState


class AngleSample(BaseModel):
    """One point on a video's per-frame elevation-angle track.

    ``elevation_angle_deg`` is the viewing angle to the PAPI midpoint computed from
    the drone's telemetry fix at this frame; ``lamps`` are the lamps observed at the
    frame (stable identity). The series of (angle, per-lamp state) points is what
    lets the Insights chart draw the real red->white transition sweep across a
    descent — instead of a single point — matching the client's AGL Altitude tool.
    Only present when a per-frame telemetry track (e.g. a DJI .SRT) was supplied.
    """

    frame_index: int = Field(ge=0)
    elevation_angle_deg: float
    lamps: list[FrameLampState] = Field(default_factory=list)
