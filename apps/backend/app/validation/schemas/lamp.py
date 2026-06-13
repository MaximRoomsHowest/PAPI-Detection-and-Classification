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
    # Measured "redness" of the lamp crop (red-channel fraction scaled to 0-255):
    # high while the lamp is red, low once it turns white. Real pixel measurement
    # backing the client's "Redness vs angle" graph; None when it can't be computed.
    redness: float | None = Field(default=None, ge=0.0, le=255.0)


class LampResult(BaseModel):
    index: int
    state: LampState
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox | None = None
    # True when the state was inferred from runway geometry + drone angle rather
    # than directly detected by YOLO. The state still carries the inferred red/white
    # value so the global PAPI verdict can use it, while the UI can disclose it.
    inferred: bool = False
    inference_note: str | None = None
    # Measured red-channel redness of this lamp (0-255, high=red); None when the
    # crop pixels weren't available. Additive — drives the Redness-vs-angle chart.
    redness: float | None = Field(default=None, ge=0.0, le=255.0)


class FrameLampState(BaseModel):
    """One lamp's classified colour at a single frame, by display Light 1..4 slot.

    Lighter than ``LampResult`` (no bbox): the per-frame angle track only needs the
    lamp index, its colour, the detection confidence, and the measured redness for
    the chart.
    """

    index: int = Field(ge=1, le=4)
    state: LampState
    confidence: float = Field(ge=0.0, le=1.0)
    # Measured red-channel redness (0-255, high=red) at this frame; None if absent.
    redness: float | None = Field(default=None, ge=0.0, le=255.0)
