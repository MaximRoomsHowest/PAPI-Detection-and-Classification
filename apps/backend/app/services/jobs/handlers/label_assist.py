"""Assisted-labeling job handler.

Runs an existing model over the dataset's staged raw images to produce CANDIDATE
YOLO labels (with a 6th confidence field for the review UI). The operator reviews
and corrects these in the frontend, then the commit endpoint writes clean 5-field
labels into the proper split. Like evaluation, this loads its OWN YOLO instance
and never holds the inference lock, so the live demo stays responsive.
"""

from __future__ import annotations

from typing import Any

from app.services.datasets import (
    CANDIDATES_DIR,
    IMAGE_SUFFIXES,
    STAGING_SPLIT,
    dataset_root,
)
from app.services.jobs.runner import JobContext
from app.services.model_registry import resolve_weights_path


def run_label_assist(params: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    model_id = params["model_id"]
    dataset_id = params["dataset_id"]
    conf = float(params.get("conf") or ctx.settings.confidence_threshold)

    ctx.progress("loading weights", 0.05)
    weights = resolve_weights_path(ctx.settings, model_id)
    root = dataset_root(ctx.settings, dataset_id)
    staging = root / "images" / STAGING_SPLIT
    candidates = root / "labels" / CANDIDATES_DIR
    candidates.mkdir(parents=True, exist_ok=True)

    images = (
        sorted(p for p in staging.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        if staging.is_dir()
        else []
    )
    if not images:
        raise RuntimeError("No staged images to label.")

    from ultralytics import YOLO

    model = YOLO(str(weights))
    total = len(images)
    imgsz = ctx.settings.inference_imgsz
    iou = ctx.settings.inference_iou

    for index, image in enumerate(images):
        ctx.check_cancelled()
        result = model.predict(str(image), imgsz=imgsz, conf=conf, iou=iou, verbose=False)[0]
        lines: list[str] = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            for cls_id, xywhn, score in zip(
                boxes.cls.tolist(), boxes.xywhn.tolist(), boxes.conf.tolist(), strict=True
            ):
                cx, cy, bw, bh = (float(v) for v in xywhn)
                # 6th field = confidence (non-standard, only read by the review UI).
                lines.append(f"{int(cls_id)} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} {float(score):.4f}")
        (candidates / f"{image.stem}.txt").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        ctx.progress(f"labeling {index + 1}/{total}", (index + 1) / total)

    return {"dataset_id": dataset_id, "model_id": model_id, "n_images": total}
