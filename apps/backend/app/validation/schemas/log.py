from pydantic import BaseModel

from app.validation.schemas.common import GlobalState, MediaType


class LogListItem(BaseModel):
    id: str
    media_type: MediaType
    runway_id: str
    drone_id: str | None
    original_filename: str
    model_id: str | None = None
    model_label: str | None = None
    model_role: str | None = None
    global_state: GlobalState
    confidence: float
    angle_available: bool
    elevation_angle_deg: float | None
    frame_count: int
    processing_ms: int
    # Partial-result flags mirrored from result_json so the history list and UI
    # badges can mark cap-truncated / decode-shortfall analyses without fetching
    # every log's detail payload.
    truncated_at_frame: int | None = None
    decode_shortfall: int | None = None
    # Per-global-state frame tally for video rows (derived from result_json.per_frame).
    # Lets the history table render a state-distribution bar instead of a single
    # dominant-state pill, so a time-varying clip reads differently from a still
    # image. None for images and for legacy video rows that have no per_frame.
    state_counts: dict[str, int] | None = None
    artifact_url: str | None = None
    created_at: str
