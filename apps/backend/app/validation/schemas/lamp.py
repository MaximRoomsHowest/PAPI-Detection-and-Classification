from pydantic import BaseModel, Field

from app.validation.schemas.common import BoundingBox, LampState


class Detection(BaseModel):
    """A single raw YOLO detection.

    Typed replacement for the previous ``list[dict]`` so the response contract is
    self-documenting and validated (audit IMP-BE-8). Pydantic coerces the dicts the
    inference service already builds, so no call site changes.
    """

    class_id: int
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox
    # ByteTrack track id when the frame was analysed with tracking (video path);
    # None for single-image predictions. Used to detect temporal red<->white
    # transitions per lamp across frames.
    track_id: int | None = None


class LampResult(BaseModel):
    index: int
    state: LampState
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox | None = None


class FrameLampState(BaseModel):
    """One lamp's classified colour at a single frame, by STABLE ByteTrack identity.

    Lighter than ``LampResult`` (no bbox): the per-frame angle track only needs the
    lamp index, its colour, and the detection confidence for the chart hover.
    """

    index: int = Field(ge=1, le=4)
    state: LampState
    confidence: float = Field(ge=0.0, le=1.0)
