from functools import lru_cache
from pathlib import Path
import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PAPI Backend"
    database_url: str = "postgresql+psycopg://papi:papi@localhost:5434/papi_backend"
    model_path: Path = Field(default=BACKEND_ROOT / "models" / "best.pt", alias="PAPI_MODEL_PATH")
    storage_dir: Path = Field(default=BACKEND_ROOT / "storage", alias="PAPI_STORAGE_DIR")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="PAPI_CORS_ORIGINS",
    )
    confidence_threshold: float = Field(default=0.4, alias="PAPI_CONFIDENCE_THRESHOLD")
    video_history_size: int = Field(default=5, alias="PAPI_VIDEO_HISTORY_SIZE")

    @field_validator("model_path", "storage_dir")
    @classmethod
    def resolve_backend_relative_path(cls, value: Path) -> Path:
        if value.is_absolute():
            return value
        return BACKEND_ROOT / value

    @property
    def cors_origin_list(self) -> list[str]:
        value = self.cors_origins.strip()
        if value.startswith("["):
            return [str(origin).strip() for origin in json.loads(value) if str(origin).strip()]
        return [origin.strip() for origin in value.split(",") if origin.strip()]

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
