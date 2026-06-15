"""Training/evaluation dataset table.

A dataset is a YOLO-format bundle on disk (under ``PAPI_DATASETS_DIR/<id>/``):
``images/{train,val,test}/``, ``labels/{train,val,test}/``, the split index files
``train.txt``/``val.txt``/``test.txt``, and a ``data.yaml`` — exactly the layout the
existing trainer (``workflows/scripts/train_transition_model.py``) and evaluator
(``workflows/scripts/evaluate_transition_model.py``) already consume, so neither
script needs to change.

Three sources:
* ``bundle``   — operator uploaded a prepared labelled YOLO zip.
* ``assisted`` — operator uploaded raw images; an existing model pre-annotated them
  and the operator reviewed/corrected the boxes before committing.
* ``builtin``  — app-shipped per-role evaluation set, seeded on startup from
  ``data/eval/`` and protected from deletion (see ``services/datasets_seed.py``).
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.analysis_log import new_id, utcnow_aware


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    # "bundle" | "assisted" | "builtin"
    source: Mapped[str] = mapped_column(String(32), default="bundle")
    # "ready" (usable for train/eval) | "labeling" (assisted job pending/in review) |
    # "draft" (created, nothing committed yet).
    status: Mapped[str] = mapped_column(String(24), default="ready")
    # Absolute dataset directory under PAPI_DATASETS_DIR.
    storage_path: Mapped[str] = mapped_column(Text)
    # {0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"}.
    class_names_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    n_train: Mapped[int] = mapped_column(Integer, default=0)
    n_val: Mapped[int] = mapped_column(Integer, default=0)
    n_test: Mapped[int] = mapped_column(Integer, default=0)
    data_yaml_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow_aware)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow_aware, onupdate=utcnow_aware
    )
