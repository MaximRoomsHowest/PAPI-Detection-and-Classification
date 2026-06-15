"""Seed the built-in evaluation datasets and score every registry model whose
weights are present against its role-matched built-in set, writing the metrics
back into the model registry (so the Models page cards show them).

Role matching: a 3-class (transition) model is scored on ``builtin-transition-3class``;
a 2-class detector on ``builtin-detector-redwhite`` — each model is evaluated only on
the classes it predicts (no nc mismatch, no unfair penalty).

Run::

    .venv/Scripts/python workflows/scripts/evaluate_builtin.py

Models whose weights are absent in this checkout are reported as skipped; re-run in a
deployment that has them (or upload them) to populate their metrics.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "apps" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _builtin_for(entry) -> str:
    """The role-matched built-in dataset id for a registry entry."""
    if (entry.class_count or 2) >= 3:
        return "builtin-transition-3class"
    return "builtin-detector-redwhite"


def main() -> int:
    from app.config import get_settings
    from app.database import get_sessionmaker, init_db
    from app.repositories.model_registry import ModelRegistryRepository
    from app.services.datasets import dataset_root
    from app.services.datasets_seed import seed_builtin_datasets
    from app.services.jobs.handlers.evaluate import _name_map, _to_val_metrics
    from app.services.model_registry import build_registry_from_db, load_model_registry

    settings = get_settings()
    # Be explicit about WHERE this writes: the script obeys the configured DATABASE_URL,
    # which by default is the Postgres the Docker stack also uses. Writing built-in
    # dataset ROWS there while the FILES land under this host's datasets_dir leaves the
    # container with "ready" rows whose data.yaml it can't see. Print both so a shared
    # DB is never a silent surprise — set PAPI_DATABASE_URL to target a specific store.
    print(f"DB:       {settings.database_url}")
    print(f"datasets: {settings.datasets_dir}")
    init_db()

    # Seed the model registry + the built-in datasets (both idempotent) so the
    # registry rows exist to write metrics into and the data.yaml files are on disk.
    session = get_sessionmaker()()
    try:
        frozen = load_model_registry(settings)
        repo = ModelRegistryRepository(session)
        repo.seed_from_frozen(frozen)
        repo.reconcile_builtins_from_frozen(frozen)
        seed_builtin_datasets(settings, session)
    finally:
        session.close()

    registry = build_registry_from_db(settings)
    from ultralytics import YOLO

    scored: list[tuple[str, str, dict]] = []
    skipped: list[tuple[str, str]] = []

    for entry in registry.entries:
        if not entry.available:
            skipped.append((entry.id, "weights not present in this checkout"))
            continue
        ds_id = _builtin_for(entry)
        data_yaml = dataset_root(settings, ds_id) / "data.yaml"
        if not data_yaml.is_file():
            skipped.append((entry.id, f"built-in dataset '{ds_id}' not seeded"))
            continue

        print(f"Evaluating '{entry.id}' on '{ds_id}' (split=test) ...", flush=True)
        run_name = f"builtin-{entry.id}"
        model = YOLO(str(entry.path))
        metrics = model.val(
            data=str(data_yaml),
            split="test",
            imgsz=settings.inference_imgsz,
            iou=0.5,
            conf=0.001,
            batch=4,
            workers=0,  # Windows-safe; the set is tiny so this is fast anyway
            project=str(settings.jobs_dir / "eval"),
            name=run_name,
            exist_ok=True,
            verbose=False,
        )
        val_metrics = _to_val_metrics(metrics, _name_map(model, ds_id, settings), "test")
        shutil.rmtree(settings.jobs_dir / "eval" / run_name, ignore_errors=True)

        session = get_sessionmaker()()
        try:
            ModelRegistryRepository(session).update_val_metrics(entry.id, val_metrics, "test")
        finally:
            session.close()
        scored.append((entry.id, ds_id, val_metrics))
        print(
            f"  {entry.id}: map50={val_metrics.get('map50')} map50_95={val_metrics.get('map50_95')} "
            f"P={val_metrics.get('precision')} R={val_metrics.get('recall')}",
            flush=True,
        )

    print("\n=== summary ===")
    for mid, ds_id, vm in scored:
        print(f"SCORED  {mid} on {ds_id}: map50={vm.get('map50')} map50_95={vm.get('map50_95')}")
    for mid, reason in skipped:
        print(f"SKIPPED {mid}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
