import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
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
    # docker-compose, dev, and CI should stay on the default ("local").
    environment: str = Field(default="local", alias="PAPI_ENV")
    database_url: str = "postgresql+psycopg://papi:papi@localhost:5434/papi_backend"
    model_path: Path = Field(default=REPO_ROOT / "models" / "serving" / "best.pt", alias="PAPI_MODEL_PATH")
    storage_dir: Path = Field(default=BACKEND_ROOT / "storage", alias="PAPI_STORAGE_DIR")
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
    video_history_size: int = Field(default=5, alias="PAPI_VIDEO_HISTORY_SIZE")
    max_upload_mb: int = Field(default=100, alias="PAPI_MAX_UPLOAD_MB")
    max_video_frames: int = Field(default=600, alias="PAPI_MAX_VIDEO_FRAMES")
    max_video_seconds: int = Field(default=30, alias="PAPI_MAX_VIDEO_SECONDS")

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

    @field_validator("model_path", "storage_dir")
    @classmethod
    def resolve_backend_relative_path(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        return (BACKEND_ROOT / value).resolve()

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
