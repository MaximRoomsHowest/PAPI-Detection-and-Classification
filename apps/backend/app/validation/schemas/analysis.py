from pydantic import BaseModel, Field

from app.validation.schemas.angle import (
    AngleResult,
    AngleSample,
    FramePoint,
    TransitionEvent,
)
from app.validation.schemas.common import GlobalState, MediaType
from app.validation.schemas.lamp import Detection, LampResult


class AnalysisPayload(BaseModel):
    log_id: str | None = None
    media_type: MediaType
    original_filename: str
    runway_id: str
    drone_id: str | None = None
    global_state: GlobalState
    model_id: str | None = None
    model_label: str | None = None
    model_role: str | None = None
    lamps: list[LampResult]
    # Aggregate detection confidence for the analysis — a probability, so [0, 1].
    confidence: float = Field(ge=0.0, le=1.0)
    frame_count: int
    processing_ms: int
    angle: AngleResult
    artifact_url: str | None = None
    detections: list[Detection] = Field(default_factory=list)
    # Temporal red<->white transitions detected across video frames (empty for
    # single images, which can't show a switch). Each carries the associated
    # viewing angle when drone telemetry was supplied.
    transitions: list[TransitionEvent] = Field(default_factory=list)
    # Which method produced ``transitions``: "tracking" (temporal red<->white flips on the serving
    # model) or "model" (learned class-2 events from the 3-class detector). Echoes the method that
    # actually ran — if "model" was requested but no 3-class model was available, this reads
    # "tracking" (graceful fallback), so the UI can tell the user what it is looking at.
    transition_method: str = "tracking"
    # Raw per-frame confidence + verdict for video / folder-sequence analyses
    # (empty for single images). Drives the Live Demo frame-by-frame confidence
    # chart; these are the per-frame values BEFORE the overlay's sliding-window
    # smoothing, so the curve shows the model's true frame-to-frame behaviour.
    per_frame: list[FramePoint] = Field(default_factory=list)
    # Per-frame elevation-angle track — populated only when a per-frame telemetry
    # track (DJI .SRT or a multi-row CSV/JSON) was supplied for a video/sequence.
    # Each entry pairs a frame's viewing angle with the lamps observed at that frame,
    # so the Insights angle-vs-state chart shows the genuine red<->white sweep across
    # the descent (a single image / single fix leaves this empty and the chart falls
    # back to one point per lamp).
    angle_track: list[AngleSample] = Field(default_factory=list)


class FrameBatchPayload(BaseModel):
    """Response shape for `POST /api/analyze-frames` — batch analysis of multiple images
    (used by the frontend's folder upload feature)."""
    frame_count: int
    processing_ms: int
    results: list[AnalysisPayload]
