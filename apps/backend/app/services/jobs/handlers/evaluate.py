"""Evaluation job handler: run ``YOLO.val()`` and write back ValMetrics.

Ports ``workflows/scripts/evaluate_transition_model.evaluate`` — crucially the
``ap_class_index`` mapping (Ultralytics orders per-class arrays by POSITION among
classes present in the split, not by raw class id; indexing by class id silently
misattributes red<->white when a class is absent). Results are mapped into the
existing ValMetrics shape so the Insights ``ModelPerformance`` panel renders them
unchanged, and persisted to the model's registry row.
"""

from __future__ import annotations

import logging
import shutil
from typing import Any

from app.database import get_sessionmaker
from app.repositories.model_registry import ModelRegistryRepository
from app.services.datasets import DEFAULT_CLASS_NAMES, dataset_root
from app.services.jobs.contracts import JobContext
from app.services.model_registry import resolve_weights_path

logger = logging.getLogger(__name__)


def _name_map(model: Any, dataset_id: str, settings) -> dict[int, str]:
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        try:
            return {int(k): str(v) for k, v in names.items()}
        except (TypeError, ValueError):
            pass
    # Fall back to the dataset's class names, then the project defaults.
    session = get_sessionmaker()()
    try:
        from app.repositories.datasets import DatasetRepository

        dataset = DatasetRepository(session).get(dataset_id)
        if dataset and isinstance(dataset.class_names_json, dict):
            try:
                return {int(k): str(v) for k, v in dataset.class_names_json.items()}
            except (TypeError, ValueError):
                pass
    finally:
        session.close()
    return dict(DEFAULT_CLASS_NAMES)


def _to_val_metrics(metrics: Any, name_map: dict[int, str], split: str) -> dict[str, Any]:
    box = metrics.box
    per_class: dict[str, dict[str, float]] = {}
    # ap_class_index is a numpy array at runtime; `array or []` raises "truth value
    # ambiguous", so normalise None -> [] explicitly instead of with `or`.
    ap_class_index = getattr(box, "ap_class_index", None)
    if ap_class_index is None:
        ap_class_index = []
    # zip the parallel per-class arrays rather than indexing box.p[pos]: if YOLO ever
    # returns mismatched lengths it truncates cleanly instead of raising IndexError
    # (or, worse, silently mis-attributing a metric to the wrong class).
    for raw_cls_id, p_val, r_val, ap50_val in zip(
        ap_class_index, box.p, box.r, box.ap50, strict=False
    ):
        cls_id = int(raw_cls_id)
        name = name_map.get(cls_id, str(cls_id))
        p = float(p_val)
        r = float(r_val)
        ap50 = float(ap50_val)
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        per_class[name] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "map50": round(ap50, 4),
        }
    return {
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "map50": round(float(box.map50), 4),
        "map50_95": round(float(box.map), 4),
        "per_class": per_class or None,
        "note": (
            f"Measured by in-app evaluation on the '{split}' split at the full PR curve "
            "(val-default conf=0.001, iou=0.5)."
        ),
    }


def run_evaluate(params: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    model_id = params["model_id"]
    dataset_id = params["dataset_id"]
    split = params.get("split", "test")

    ctx.progress("loading weights", 0.05)
    weights = resolve_weights_path(ctx.settings, model_id)
    root = dataset_root(ctx.settings, dataset_id)
    data_yaml = root / "data.yaml"
    if not data_yaml.is_file():
        raise RuntimeError(
            "Dataset has no data.yaml on this server (files missing, or still in labeling)."
        )

    ctx.check_cancelled()
    from ultralytics import YOLO

    model = YOLO(str(weights))
    name_map = _name_map(model, dataset_id, ctx.settings)

    ctx.progress(f"running val ({split})", 0.2)
    # Own YOLO instance + own val run dir; never touches the serving model or lock.
    metrics = model.val(
        data=str(data_yaml),
        split=split,
        imgsz=ctx.settings.inference_imgsz,
        iou=0.5,
        conf=0.001,
        batch=4,
        workers=2,
        project=str(ctx.settings.jobs_dir / "eval"),
        name=f"eval-{ctx.job_id}",
        exist_ok=True,
        verbose=False,
    )

    # A cancel requested DURING the (uninterruptible) val() call must not still write
    # metrics back to the model card — honour it before persisting.
    ctx.check_cancelled()

    ctx.progress("writing metrics", 0.85)
    val_metrics = _to_val_metrics(metrics, name_map, split)

    # The full YOLO val() run tree (plots, mosaics, CSV) is never referenced again
    # once the scalar metrics are out — delete it so the jobs volume doesn't grow by
    # tens of MB per evaluation. After extraction, so a deletion error can't mask a
    # real metrics failure.
    shutil.rmtree(ctx.settings.jobs_dir / "eval" / f"eval-{ctx.job_id}", ignore_errors=True)

    session = get_sessionmaker()()
    try:
        ModelRegistryRepository(session).update_val_metrics(model_id, val_metrics, split)
    finally:
        session.close()

    # Surface the fresh metrics on /api/model immediately.
    try:
        from app.services.inference import get_inference_service

        get_inference_service().reload_registry()
    except Exception as exc:  # noqa: BLE001 - metrics are already persisted; reload is best-effort
        logger.warning("Registry reload after evaluation failed: %s", exc)

    return {
        "model_id": model_id,
        "dataset_id": dataset_id,
        "split": split,
        "val_metrics": val_metrics,
    }
