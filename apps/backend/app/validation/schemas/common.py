from typing import Literal

from pydantic import BaseModel, model_validator

# Per-frame lamp verdict. "obscured" = a lamp position the detector did not find
# (occluded, too dim/distant, or physically missing) — surfaced as a real category
# so the insights charts can show it instead of silently dropping the lamp. The
# "transition" label is temporal (a red<->white switch across frames; see TransitionEvent).
LampState = Literal["white", "red", "transition", "obscured", "unknown"]
MediaType = Literal["image", "video"]
# The five glidepath verdicts plus the geometry-derived "transition" and the
# "unknown" fallback (audit B-MAJ-10). Matches global_state_from_lamps + the papi
# package's decoder, so the response contract is self-documenting and validated.
GlobalState = Literal[
    "far_too_high",
    "too_high",
    "correct_glidepath",
    "too_low",
    "far_too_low",
    "transition",
    "unknown",
]


class BoundingBox(BaseModel):
    """Pixel-space detection box in top-left-origin image coordinates.

    ``(x1, y1)`` is the top-left corner and ``(x2, y2)`` the bottom-right, so a
    well-formed box always has ``x2 >= x1`` and ``y2 >= y1`` (zero-area boxes are
    allowed — a single-pixel lamp is legitimate). The validator rejects inverted
    coordinates early instead of letting them propagate into the crop/overlay math.
    """

    x1: int
    y1: int
    x2: int
    y2: int

    @model_validator(mode="after")
    def _check_ordering(self) -> "BoundingBox":
        if self.x2 < self.x1:
            raise ValueError("x2 must be >= x1")
        if self.y2 < self.y1:
            raise ValueError("y2 must be >= y1")
        return self
