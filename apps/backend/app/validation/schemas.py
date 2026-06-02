from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


class AnalysisPayload(BaseModel):
    log_id: str | None = None
    media_type: MediaType
    original_filename: str
    runway_id: str
    drone_id: str | None = None
    global_state: GlobalState
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


class FrameBatchPayload(BaseModel):
    """Response shape for `POST /api/analyze-frames` — batch analysis of multiple images
    (used by the frontend's folder upload feature)."""
    frame_count: int
    processing_ms: int
    results: list[AnalysisPayload]


class LogListItem(BaseModel):
    id: str
    media_type: MediaType
    runway_id: str
    drone_id: str | None
    original_filename: str
    global_state: GlobalState
    confidence: float
    angle_available: bool
    elevation_angle_deg: float | None
    frame_count: int
    processing_ms: int
    artifact_url: str | None = None
    created_at: str


class ValMetrics(BaseModel):
    """Validation-split metrics for the serving model, read from its model_card.json.

    These are box (B) detection metrics on the val split — not the held-out test
    regime and not per-class. The ``note`` carries that caveat to the UI so nothing
    on screen overstates the numbers (project honesty principle).
    """

    selection: str | None = None
    epoch: int | None = None
    precision: float | None = None
    recall: float | None = None
    map50: float | None = None
    map50_95: float | None = None
    note: str | None = None


class ModelInfo(BaseModel):
    model_path: str
    model_filename: str
    model_format: str
    backend_type: str
    exists: bool
    file_size_mb: float | None = None
    confidence_threshold: float
    device: str
    loaded: bool
    # Provenance (audit IMP-BE-1 / IMP-SRV-3): SHA-256 of the on-disk weights plus
    # the training-run lineage + val metrics from models/serving/model_card.json, so
    # /api/model can answer "which run is serving and how accurate is it?". All
    # optional — a bare-weights dev checkout (no model_card.json) returns None.
    sha256: str | None = None
    classes: dict[int, str] | None = None
    model_id: str | None = None
    training_run: str | None = None
    base_weights: str | None = None
    dataset_split_evaluated: str | None = None
    val_metrics: ValMetrics | None = None
    loaded_at: str | None = None


class InferenceStats(BaseModel):
    # Aggregated over the WHOLE analysis_logs table (audit IMP-BE-2), not just the
    # most-recent 100 rows as before. ``sample_size`` is kept (== total_analyses) so
    # existing consumers don't break; the breakdowns are new.
    sample_size: int
    total_analyses: int
    image_count: int
    video_count: int
    avg_processing_ms: float | None = None
    p50_processing_ms: int | None = None
    p95_processing_ms: int | None = None
    avg_confidence: float | None = None
    by_runway: dict[str, int] = Field(default_factory=dict)
    by_global_state: dict[str, int] = Field(default_factory=dict)
    by_media_type: dict[str, int] = Field(default_factory=dict)
    first_analysis_at: str | None = None
    latest_created_at: str | None = None


class SystemInfo(BaseModel):
    """Host / runtime facts for the demo (audit IMP-BE-7).

    Honestly replaces the fabricated "edge memory" card removed in audit F-CRIT-2 —
    every value here is read from the running host, not invented.
    """

    platform: str
    python_version: str
    cpu_count: int | None = None
    torch_available: bool = False
    cuda_available: bool = False
    cuda_device_count: int = 0
    device_configured: str
    app_version: str


class RunwayLight(BaseModel):
    point: int
    latitude: float
    longitude: float
    altitude_m: float


class RunwayResponse(BaseModel):
    id: str
    label: str
    lights: list[RunwayLight]

