"""Background-job table.

The backend serialises inference on a single re-entrant lock and has no task
queue. Evaluation and model-assisted labeling are both longer-running than a
single request, so they run on a one-worker executor whose durable state lives
HERE (not in memory): the frontend polls ``GET /api/jobs/{id}`` and a backend
restart can reconcile orphaned ``running`` rows to ``failed``.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.analysis_log import new_id, utcnow_aware


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # "evaluate" | "label_assist" | "train_prepare"
    kind: Mapped[str] = mapped_column(String(32))
    # "queued" | "running" | "succeeded" | "failed" | "cancelled"
    status: Mapped[str] = mapped_column(String(24), default="queued")
    # Coarse human-readable phase, e.g. "running val()" or "uploading dataset".
    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow_aware, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
