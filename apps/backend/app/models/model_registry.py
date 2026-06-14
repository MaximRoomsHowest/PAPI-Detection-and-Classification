"""Mutable model-registry table.

The historical registry (``models/serving/models.json``) is a frozen, read-only
file — the Docker image bind-mounts ``./models`` read-only, so it cannot absorb
operator uploads. This table makes the registry mutable: uploads, cloud-trained
models, promote-to-default and delete all write here, and ``InferenceService``
rebuilds its in-memory frozen registry from these rows on reload.

The JSON file becomes a one-time SEED: on first startup with an empty table the
three built-in entries (``small``/``nano``/``transition``) are copied in (see
``ModelRegistryRepository.seed_from_frozen``), with the committed serving
``best.pt`` marked ``protected`` so it can never be deleted from the UI.
"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.analysis_log import utcnow_aware


class ModelRegistryRow(Base):
    __tablename__ = "model_registry"

    # Registry ids are short, human-chosen handles ("small"/"nano") or generated
    # slugs for uploads; VARCHAR(96) mirrors analysis_logs.model_id so a stored id
    # always fits the History filter column too.
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    label: Mapped[str] = mapped_column(String(160))
    # "detector" (2-class red/white) or "transition" (3-class red/white/transition).
    role: Mapped[str] = mapped_column(String(32), default="detector")
    # Provenance of the weights: "builtin" (seeded from models.json) or "uploaded"
    # (operator upload — including weights trained externally and re-imported).
    source: Mapped[str] = mapped_column(String(32), default="builtin")
    # Absolute path for uploaded weights (under PAPI_USER_MODELS_DIR), or a
    # repo-relative path for seeded built-ins (resolved via _resolve_registry_path).
    storage_path: Mapped[str] = mapped_column(Text)
    class_count: Mapped[int] = mapped_column(Integer, default=2)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # Disabled entries stay listed (greyed out) so reviewers can still read their
    # card; they are never auto-selected for inference.
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The committed serving model: undeletable from the UI (it ships with the repo).
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {0: "PAPI-Red", 1: "PAPI-White", ...} — keys stored as JSON strings.
    classes_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # ValMetrics-shaped dict written by the evaluation job (top-level P/R/mAP +
    # per_class). This is the model-card "val_metrics" surfaced on /api/model.
    val_metrics_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    training_run: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_weights: Mapped[str | None] = mapped_column(Text, nullable=True)
    split_evaluated: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow_aware)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow_aware, onupdate=utcnow_aware
    )
