from pydantic import BaseModel, Field


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
    # Per-class breakdown (e.g. {"transition": {"precision": 0.0, ...}}). The registry
    # carries these for the 3-class transition model and pydantic's extra="ignore" was
    # silently dropping them — hiding exactly the number a safety reviewer comparing
    # models needs (audit PC-1).
    per_class: dict[str, dict[str, float]] | None = None
    note: str | None = None


class WeatherMetrics(BaseModel):
    """Per-condition robustness — mAP@0.5 on the held-out test split re-rendered under
    synthetic weather (pure-OpenCV augmentation). Surfaced on the Models page so a viewer
    can see how a detector holds up as conditions degrade; the ``snow`` column is the
    decisive differentiator (bright speckle mimics white lamps, so only a weather-trained
    model survives it). All optional — a model without a weather eval omits the block.
    """

    severity: str | None = None  # synthetic-weather strength evaluated ("medium" | "heavy")
    split: str | None = None  # evaluation split the conditions were measured on ("test")
    clear: float | None = None
    rain: float | None = None
    fog: float | None = None
    haze: float | None = None
    snow: float | None = None


class ModelInfo(BaseModel):
    model_id: str | None = None
    model_label: str | None = None
    model_role: str | None = None
    is_default: bool = False
    available: bool = True
    disabled_reason: str | None = None
    description: str | None = None
    # Lifecycle metadata for the management UI (DB-backed registry):
    # source = builtin | uploaded | trained; protected = committed serving model
    # (undeletable); disabled = operator-hidden but still listed; class_count is the
    # registry-declared class count (frontend fallback when live class names absent).
    source: str | None = None
    protected: bool = False
    disabled: bool = False
    class_count: int | None = None
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
    # True when the on-disk file no longer matches the loaded weights (checkpoint
    # swapped under a running service; restart pending). None when not loaded.
    weights_changed_on_disk: bool | None = None
    classes: dict[int, str] | None = None
    model_card_id: str | None = None
    training_run: str | None = None
    base_weights: str | None = None
    dataset_split_evaluated: str | None = None
    val_metrics: ValMetrics | None = None
    # Per-condition synthetic-weather robustness (mAP@0.5), when a weather eval exists
    # for this model. Drives the Models page "Weather robustness" bars + compare group.
    weather_metrics: WeatherMetrics | None = None
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
    # Per-media-type latency: a whole-video analysis spans many frames, so its
    # processing time is not comparable to a single image's — surfaced separately.
    # Null when the filtered slice has no rows of that media type.
    image_avg_processing_ms: float | None = None
    image_p50_processing_ms: int | None = None
    image_p95_processing_ms: int | None = None
    video_avg_processing_ms: float | None = None
    video_p50_processing_ms: int | None = None
    video_p95_processing_ms: int | None = None
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
