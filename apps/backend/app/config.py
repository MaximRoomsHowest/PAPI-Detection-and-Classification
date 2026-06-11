import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "PAPI Backend"
    # ``environment`` flips the security floor. In "production" the startup
    # check in main.py refuses to boot without a non-empty PAPI_API_KEY
    # (audit B-CRIT-5). Use "production" only at real deploy time; local
    # Compose, dev, and CI should stay on the default ("local").
    environment: str = Field(default="local", alias="PAPI_ENV")
    # Read from DATABASE_URL (Compose + .env.example) OR PAPI_DATABASE_URL
    # (matches every other setting's PAPI_ prefix and the production startup error
    # message). Previously only the bare field name was matched, so a
    # PAPI_DATABASE_URL override was silently ignored (audit backend-tests).
    database_url: str = Field(
        default="postgresql+psycopg://papi:papi@localhost:5434/papi_backend",
        validation_alias=AliasChoices("DATABASE_URL", "PAPI_DATABASE_URL"),
    )
    model_path: Path = Field(default=REPO_ROOT / "models" / "serving" / "best.pt", alias="PAPI_MODEL_PATH")
    model_registry_path: Path = Field(
        default=REPO_ROOT / "models" / "serving" / "models.json",
        alias="PAPI_MODEL_REGISTRY_PATH",
    )
    # Optional 3-class transition-aware model (red/white/transition) used by the "model" transition
    # method. Kept separate from model_path so the 2-class serving model and the experimental 3-class
    # model coexist without promoting one. When unset or absent, the "model" method gracefully falls
    # back to the temporal "tracking" method.
    transition_model_path: Path | None = Field(default=None, alias="PAPI_TRANSITION_MODEL_PATH")
    # Transition method when a request omits it: "tracking" (temporal red<->white flips on the
    # serving model) or "model" (learned class-2 events from the 3-class model).
    default_transition_method: str = Field(default="tracking", alias="PAPI_TRANSITION_METHOD")
    device: str = Field(default="cpu", alias="PAPI_DEVICE")
    storage_dir: Path = Field(default=BACKEND_ROOT / "storage", alias="PAPI_STORAGE_DIR")
    storage_backend: str = Field(default="local", alias="PAPI_STORAGE_BACKEND")
    blob_container: str = Field(default="papi-media", alias="PAPI_BLOB_CONTAINER")
    azure_storage_connection_string: str | None = Field(default=None, alias="AZURE_STORAGE_CONNECTION_STRING")
    azure_storage_account_url: str | None = Field(default=None, alias="AZURE_STORAGE_ACCOUNT_URL")
    api_key: str | None = Field(default=None, alias="PAPI_API_KEY")
    # NoDecode disables pydantic-settings' built-in JSON decode for env values
    # so the @field_validator below receives the raw string and can parse
    # comma-separated lists. Without this the env source raises SettingsError
    # before the validator runs and the backend container crashes at startup
    # (see audit SMOKE-CRIT-2).
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ],
        alias="PAPI_CORS_ORIGINS",
    )
    confidence_threshold: float = Field(default=0.4, ge=0.0, le=1.0, alias="PAPI_CONFIDENCE_THRESHOLD")
    # Inference input size + NMS IoU, made EXPLICIT so every model runs at its trained resolution
    # instead of relying on the checkpoint's implicit imgsz override. best.pt carries imgsz=1280 so
    # predict already uses it, but a re-export, an ONNX export, or the registry's nano/transition
    # checkpoints could silently fall back to Ultralytics' 640 default — which roughly quarters the
    # pixels on the small/distant PAPI lamps and degrades recall (audit). All serving checkpoints are
    # trained at 1280; the NMS IoU keeps the predict default 0.7.
    inference_imgsz: int = Field(default=1280, ge=320, le=4096, alias="PAPI_INFERENCE_IMGSZ")
    inference_iou: float = Field(default=0.7, ge=0.0, le=1.0, alias="PAPI_INFERENCE_IOU")
    # Per-file upload ceiling in megabytes (media.save_upload streams and aborts
    # past max_upload_mb * 1024 * 1024 bytes). >= 1 MB; upper bound keeps a typo'd
    # env var from effectively disabling the limit.
    max_upload_mb: int = Field(default=100, ge=1, le=10000, alias="PAPI_MAX_UPLOAD_MB")
    # Hard cap on DECODED pixels per image/frame. The byte-size cap above does NOT bound
    # decode amplification: a small, highly-compressed file (or video frame) can decode to
    # gigabytes — a "decompression bomb". 80 MP covers legitimate high-res drone stills and
    # 4K/8K video while rejecting bomb-sized frames before they are decoded into RAM.
    max_image_megapixels: int = Field(default=80, ge=1, le=2000, alias="PAPI_MAX_IMAGE_MEGAPIXELS")
    # Hard cap on frames decoded from an uploaded video. >= 1; upper bound keeps a
    # runaway value from holding the worker indefinitely.
    max_video_frames: int = Field(default=600, ge=1, le=100000, alias="PAPI_MAX_VIDEO_FRAMES")
    # Duration-based frame cap (combined with max_video_frames, the lower wins).
    # 0 is a supported sentinel meaning "no duration cap" (inference._video_frame_limit),
    # so the lower bound stays ge=0 rather than gt=0. Upper bound guards against typos.
    max_video_seconds: int = Field(default=30, ge=0, le=86400, alias="PAPI_MAX_VIDEO_SECONDS")
    # Aggregate upper bound on a single POST /api/analyze-frames call. The
    # backend processes frames sequentially per request, so an unbounded
    # list would hold the worker for minutes; per-file size is checked,
    # count was not. Configurable via env so the demo can raise it for
    # benchmarking (audit B-MAJ-5).
    max_batch_frames: int = Field(default=200, ge=1, le=100000, alias="PAPI_MAX_BATCH_FRAMES")
    # Aggregate upload-body budget for folder/batch endpoints. The per-file
    # PAPI_MAX_UPLOAD_MB cap still applies, but without this a default
    # 200-frame batch could carry 20 GB of files in one request.
    max_batch_upload_mb: int = Field(default=400, ge=1, le=10000, alias="PAPI_MAX_BATCH_UPLOAD_MB")
    # FPS assigned to a folder->video sequence: the uploaded images are treated as
    # consecutive video frames, so this sets annotated-playback speed and the
    # transition frame-gap timing. It does not affect detection.
    sequence_fps: float = Field(default=4.0, gt=0, le=120.0, alias="PAPI_SEQUENCE_FPS")
    # Postgres connection-pool sizing (ignored on SQLite, which uses StaticPool).
    # SQLAlchemy's defaults (5 + 10 overflow) sit below Starlette's default
    # 40-thread pool that runs the sync endpoints; 10 + 20 keeps headroom for a
    # burst of logs/stats/runways requests without holding 40 idle connections.
    db_pool_size: int = Field(default=10, ge=1, le=100, alias="PAPI_DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, ge=0, le=200, alias="PAPI_DB_MAX_OVERFLOW")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(origin).strip() for origin in parsed if str(origin).strip()]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("model_path", "model_registry_path", "storage_dir")
    @classmethod
    def resolve_backend_relative_path(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        return (BACKEND_ROOT / value).resolve()

    @field_validator("transition_model_path", mode="before")
    @classmethod
    def empty_transition_path_is_none(cls, value: object) -> object:
        # compose forwards PAPI_TRANSITION_MODEL_PATH with an empty default; an
        # empty string must mean "not installed", not Path(".") resolved against
        # the backend root (audit IS-2).
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("transition_model_path")
    @classmethod
    def resolve_optional_backend_relative_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value if value.is_absolute() else (BACKEND_ROOT / value).resolve()

    @field_validator("default_transition_method")
    @classmethod
    def validate_default_transition_method(cls, value: str) -> str:
        normalized = (value or "tracking").strip().lower()
        if normalized not in ("tracking", "model"):
            raise ValueError("default_transition_method must be 'tracking' or 'model'")
        return normalized

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, value: str) -> str:
        normalized = (value or "local").strip().lower()
        if normalized not in ("local", "azure_blob"):
            raise ValueError("storage_backend must be 'local' or 'azure_blob'")
        return normalized

    @property
    def uploads_dir(self) -> Path:
        return self.storage_dir / "uploads"

    @property
    def exports_dir(self) -> Path:
        return self.storage_dir / "exports"

    @property
    def tmp_dir(self) -> Path:
        return self.storage_dir / "tmp"

    def ensure_storage(self) -> None:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_storage()
    return settings
