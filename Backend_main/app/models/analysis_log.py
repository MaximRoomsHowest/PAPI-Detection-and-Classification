from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def new_id() -> str:
    return str(uuid4())


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    media_type: Mapped[str] = mapped_column(String(24), index=True)
    runway_id: Mapped[str] = mapped_column(String(32), default="papi_06", index=True)
    drone_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    artifact_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    global_state: Mapped[str] = mapped_column(String(64), index=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

