"""Persistence for the mutable model registry (``model_registry`` table).

All registry mutation goes through here: seeding the built-ins from the frozen
``models.json`` on first boot, inserting uploaded/trained models, promoting a
default, disabling/deleting, and writing back evaluation metrics. The service
layer turns these rows into the in-memory frozen ``ModelRegistry`` on reload.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_registry import ModelRegistryRow


class ProtectedModelError(RuntimeError):
    """Raised when an operation is refused because the model is protected
    (the committed serving model) — surfaced as a 400."""


class DefaultModelError(RuntimeError):
    """Raised when deleting the current default without promoting a replacement
    first — surfaced as a 409."""


class ModelRegistryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[ModelRegistryRow]:
        return list(self.db.scalars(select(ModelRegistryRow).order_by(ModelRegistryRow.created_at)).all())

    def get(self, model_id: str) -> ModelRegistryRow | None:
        return self.db.get(ModelRegistryRow, model_id)

    def is_empty(self) -> bool:
        return self.db.scalar(select(ModelRegistryRow.id).limit(1)) is None

    def insert(self, row: ModelRegistryRow, *, commit: bool = True) -> ModelRegistryRow:
        self.db.add(row)
        if commit:
            self.db.commit()
            self.db.refresh(row)
        return row

    def set_default(self, model_id: str) -> ModelRegistryRow:
        """Transactionally make ``model_id`` the sole default. Refuses disabled models."""
        target = self.get(model_id)
        if target is None:
            raise KeyError(model_id)
        if target.disabled:
            raise ValueError(f"Model '{model_id}' is disabled and cannot be promoted to default.")
        for row in self.list_all():
            row.is_default = row.id == model_id
        self.db.commit()
        self.db.refresh(target)
        return target

    def disable(self, model_id: str, reason: str | None = None) -> ModelRegistryRow:
        row = self.get(model_id)
        if row is None:
            raise KeyError(model_id)
        if row.is_default:
            raise DefaultModelError(
                f"Model '{model_id}' is the current default; promote another model before disabling it."
            )
        row.disabled = True
        row.disabled_reason = reason or "Disabled by operator."
        self.db.commit()
        self.db.refresh(row)
        return row

    def enable(self, model_id: str) -> ModelRegistryRow:
        row = self.get(model_id)
        if row is None:
            raise KeyError(model_id)
        row.disabled = False
        row.disabled_reason = None
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, model_id: str) -> ModelRegistryRow:
        """Delete a registry row, returning it so the caller can unlink its weights.

        Refuses the committed serving model (protected) and the current default
        (promote a replacement first) so the demo can never be left unservable.
        """
        row = self.get(model_id)
        if row is None:
            raise KeyError(model_id)
        if row.protected:
            raise ProtectedModelError(
                f"Model '{model_id}' is the committed serving model and cannot be deleted."
            )
        if row.is_default:
            raise DefaultModelError(
                f"Model '{model_id}' is the current default; promote another model before deleting it."
            )
        self.db.delete(row)
        self.db.commit()
        return row

    def update_val_metrics(self, model_id: str, metrics: dict[str, Any], split: str | None = None) -> ModelRegistryRow:
        row = self.get(model_id)
        if row is None:
            raise KeyError(model_id)
        row.val_metrics_json = metrics
        if split:
            row.split_evaluated = split[:32]
        self.db.commit()
        self.db.refresh(row)
        return row

    def seed_from_frozen(self, frozen) -> int:
        """Idempotently copy the frozen ``models.json`` registry into the table.

        Only runs when the table is empty (first boot / fresh DB), so it never
        clobbers operator edits. The default entry and the committed serving
        ``best.pt`` are flagged so promote/delete protections work immediately.
        Returns the number of rows seeded.
        """
        if not self.is_empty():
            return 0
        seeded = 0
        for entry in frozen.entries:
            card = entry.card or {}
            classes = card.get("classes")
            classes_json = classes if isinstance(classes, dict) else None
            val_metrics = card.get("val_metrics") if isinstance(card.get("val_metrics"), dict) else None
            is_default = entry.id == frozen.default_model_id
            # The committed serving weights are the protected, undeletable anchor.
            protected = is_default and entry.role != "transition"
            self.db.add(
                ModelRegistryRow(
                    id=entry.id,
                    label=entry.label,
                    role=entry.role,
                    source="builtin",
                    # Store the path as declared (repo-relative for built-ins); the
                    # service resolves it through _resolve_registry_path on reload.
                    storage_path=str(entry.path),
                    class_count=entry.class_count,
                    is_default=is_default,
                    disabled=False,
                    disabled_reason=entry.disabled_reason,
                    protected=protected,
                    description=entry.description,
                    classes_json=classes_json,
                    val_metrics_json=val_metrics,
                    training_run=card.get("training_run"),
                    base_weights=card.get("base_weights"),
                    split_evaluated=card.get("split_evaluated"),
                )
            )
            seeded += 1
        self.db.commit()
        return seeded
