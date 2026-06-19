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


def _row_kwargs_from_frozen_entry(entry, default_model_id: str, *, is_default: bool) -> dict[str, Any]:
    card = entry.card or {}
    classes = card.get("classes")
    classes_json = classes if isinstance(classes, dict) else None
    val_metrics = card.get("val_metrics") if isinstance(card.get("val_metrics"), dict) else None
    protected = entry.id == default_model_id and entry.role != "transition"
    return {
        "id": entry.id,
        "label": entry.label,
        "role": entry.role,
        "source": "builtin",
        # Store the resolved frozen path. This also repairs old DB rows that were
        # seeded with a bare "best.pt" and therefore made existing local DBs not-ready.
        "storage_path": str(entry.path),
        "class_count": entry.class_count,
        "is_default": is_default,
        "disabled": False,
        "disabled_reason": entry.disabled_reason,
        "protected": protected,
        "description": entry.description,
        "classes_json": classes_json,
        "val_metrics_json": val_metrics,
        "training_run": card.get("training_run"),
        "base_weights": card.get("base_weights"),
        "split_evaluated": card.get("split_evaluated"),
    }


class ModelRegistryRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[ModelRegistryRow]:
        return list(self.db.scalars(select(ModelRegistryRow).order_by(ModelRegistryRow.created_at)).all())

    def get(self, model_id: str) -> ModelRegistryRow | None:
        return self.db.get(ModelRegistryRow, model_id)

    def _get_locked(self, model_id: str) -> ModelRegistryRow | None:
        """Row-locked fetch (``SELECT ... FOR UPDATE`` on Postgres; a no-op on SQLite,
        which serializes writes) so concurrent promote/disable/delete can't both pass
        their invariant checks before either commits (TOCTOU)."""
        return self.db.scalar(
            select(ModelRegistryRow).where(ModelRegistryRow.id == model_id).with_for_update()
        )

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
        target = self._get_locked(model_id)
        if target is None:
            raise KeyError(model_id)
        if target.disabled:
            raise ValueError(f"Model '{model_id}' is disabled and cannot be promoted to default.")
        # Clear every OTHER default and FLUSH before marking the target, so the
        # transaction never holds two is_default=True rows at once — the partial unique
        # index uq_model_registry_one_default is checked per-statement on SQLite, so a
        # set-new-then-clear-old order would raise IntegrityError (audit 2026-06-19).
        for row in self.list_all():
            if row.id != model_id and row.is_default:
                row.is_default = False
        self.db.flush()
        target.is_default = True
        self.db.commit()
        self.db.refresh(target)
        return target

    def disable(self, model_id: str, reason: str | None = None) -> ModelRegistryRow:
        row = self._get_locked(model_id)
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
        row = self._get_locked(model_id)
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
            is_default = entry.id == frozen.default_model_id
            self.db.add(
                ModelRegistryRow(
                    **_row_kwargs_from_frozen_entry(
                        entry,
                        frozen.default_model_id,
                        is_default=is_default,
                    )
                )
            )
            seeded += 1
        self.db.commit()
        return seeded

    def reconcile_builtins_from_frozen(self, frozen) -> int:
        """Repair existing built-in rows from the frozen registry without
        clobbering operator-managed models or the current default selection.

        This covers local/prod databases seeded by older code with incomplete
        paths such as ``best.pt``. Uploaded/trained rows are ignored, and existing
        disabled/default choices are preserved. Operator-written evaluation results
        (``val_metrics_json`` / ``split_evaluated``) are ALSO preserved: re-evaluating
        a built-in model must survive a restart, so reconcile repairs provenance/paths
        but never reverts metrics the operator produced via the Evaluate flow.
        """
        changed = 0
        rows = {row.id: row for row in self.list_all()}
        has_default = any(row.is_default for row in rows.values())
        for entry in frozen.entries:
            row = rows.get(entry.id)
            is_default = not has_default and entry.id == frozen.default_model_id
            values = _row_kwargs_from_frozen_entry(entry, frozen.default_model_id, is_default=is_default)
            if row is None:
                self.db.add(ModelRegistryRow(**values))
                has_default = has_default or is_default
                changed += 1
                continue
            if row.source not in (None, "", "builtin"):
                continue
            row_changed = False
            # NB: val_metrics_json + split_evaluated are intentionally NOT reconciled —
            # they hold operator Evaluate results that must persist across restarts.
            for field in (
                "label",
                "role",
                "source",
                "storage_path",
                "class_count",
                "protected",
                "description",
                "classes_json",
                "training_run",
                "base_weights",
            ):
                next_value = values[field]
                if getattr(row, field) != next_value:
                    setattr(row, field, next_value)
                    row_changed = True
            if not row.disabled and row.disabled_reason != values["disabled_reason"]:
                row.disabled_reason = values["disabled_reason"]
                row_changed = True
            if row_changed:
                changed += 1
        if changed:
            self.db.commit()
        return changed
