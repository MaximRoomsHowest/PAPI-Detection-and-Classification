from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utcnow_aware() -> datetime:
    """Replacement for ``datetime.utcnow()`` (deprecated in 3.12, removed in 3.14).

    Returns a timezone-aware UTC datetime that round-trips correctly through
    SQLAlchemy's ``DateTime(timezone=True)`` (audit B-CRIT-4).
    """
    return datetime.now(timezone.utc)


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    # Composite indexes for the History / GET /api/logs access pattern: filter by
    # global_state or media_type, ordered by created_at DESC. A (col, created_at)
    # b-tree also serves a lookup on `col` alone (leftmost prefix) and Postgres can
    # scan it backward for the DESC sort, so these replace the standalone
    # global_state / media_type indexes. Note: create_all only adds indexes to a
    # FRESH table; an existing deployment needs a manual CREATE INDEX (no migration
    # tool yet) (audit backend-perf).
    __table_args__ = (
        Index("ix_logs_state_created", "global_state", "created_at"),
        Index("ix_logs_media_created", "media_type", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    media_type: Mapped[str] = mapped_column(String(24))
    # String(96) (not 32): a custom runway id is "custom_" (7) + an up-to-80-char slug
    # derived from RunwayCreate.id, so 32 would overflow and raise a Postgres
    # StringDataRightTruncation → 503 that orphans the just-written artifact (SQLite
    # ignores VARCHAR width, so this only bites on Postgres). create_all only widens a
    # FRESH table; an existing deployment needs a manual
    # ALTER TABLE analysis_logs ALTER COLUMN runway_id TYPE VARCHAR(96) (audit C2).
    runway_id: Mapped[str] = mapped_column(String(96), default="papi_24", index=True)
    drone_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Which registry model produced this analysis ("small"/"nano"/"transition"),
    # promoted out of result_json so History can filter server-side (audit COL-1).
    # Width matches runway_id's VARCHAR(96). NULL on rows written before the column
    # existed — readers fall back to result_json. No index: low cardinality at demo
    # scale. Existing tables gain the column via app/migrations.py at startup.
    model_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    global_state: Mapped[str] = mapped_column(String(64))
    lamp_1_state: Mapped[str] = mapped_column(String(32), default="unknown")
    lamp_2_state: Mapped[str] = mapped_column(String(32), default="unknown")
    lamp_3_state: Mapped[str] = mapped_column(String(32), default="unknown")
    lamp_4_state: Mapped[str] = mapped_column(String(32), default="unknown")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    angle_available: Mapped[bool] = mapped_column(default=False)
    elevation_angle_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    processing_ms: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow_aware, index=True
    )

