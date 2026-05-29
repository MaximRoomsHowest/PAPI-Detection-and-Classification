from typing import Literal

from pydantic import BaseModel, Field

LampState = Literal["white", "red", "transition", "unknown"]
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
    x1: int
    y1: int
    x2: int
    y2: int


class Detection(BaseModel):
    """A single raw YOLO detection.

    Typed replacement for the previous ``list[dict]`` so the response contract is
    self-documenting and validated (audit IMP-BE-8). Pydantic coerces the dicts the
    inference service already builds, so no call site changes.
    """

    class_id: int
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox


class LampResult(BaseModel):
    index: int
    state: LampState
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: BoundingBox | None = None


class AnglePerLight(BaseModel):
    runway_lamp: int
    distance_m: float
    elevation_angle_deg: float


class AngleResult(BaseModel):
    angle_available: bool
    elevation_angle_deg: float | None = None
    per_light_angles: list[AnglePerLight] = Field(default_factory=list)
    angle_source: str | None = None
    angle_note: str


class AnalysisPayload(BaseModel):
    log_id: str | None = None
    media_type: MediaType
    original_filename: str
    runway_id: str
    drone_id: str | None = None
    global_state: GlobalState
    lamps: list[LampResult]
    confidence: float
    frame_count: int
    processing_ms: int
    angle: AngleResult
    artifact_url: str | None = None
    detections: list[Detection] = Field(default_factory=list)


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

