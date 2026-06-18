"""Training-launcher endpoint (operator-auth gated).

The backend never trains in-process. ``POST /api/training/prepare`` packages the
dataset + a runnable command for the existing trainer; the user runs it on their
own GPU and re-imports the resulting weights via the model-upload endpoint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.database import get_session
from app.repositories.datasets import DatasetRepository
from app.repositories.jobs import JobRepository
from app.repositories.model_registry import ModelRegistryRepository
from app.services.datasets import dataset_root
from app.services.training_prepare import COLOUR_SAFE_AUG, build_command, build_training_bundle
from app.validation.schemas import PrepareTrainingRequest, PrepareTrainingResponse

router = APIRouter(prefix="/api")


def _base_weights_name(settings, base_model_id: str | None, db: Session) -> str:
    if not base_model_id:
        return "yolo26s.pt"
    row = ModelRegistryRepository(db).get(base_model_id)
    if row is None:
        return "yolo26s.pt"
    from pathlib import Path

    return Path(row.storage_path).name or "yolo26s.pt"


@router.post("/training/prepare", response_model=PrepareTrainingResponse)
def prepare_training(
    payload: PrepareTrainingRequest,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> PrepareTrainingResponse:
    settings = routes.get_settings()
    if not settings.training_enabled:
        raise HTTPException(status_code=403, detail="Training is disabled.")
    dataset = DatasetRepository(db).get(payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Unknown dataset.")
    if dataset.status != "ready":
        raise HTTPException(status_code=400, detail="Dataset is not ready for training.")
    if dataset.source == "builtin":
        # Built-in eval sets are fixed, protected hold-out sets (delete is refused
        # too) — training on one would defeat their purpose as a stable benchmark.
        raise HTTPException(
            status_code=400, detail="Built-in evaluation datasets cannot be used for training."
        )

    base = _base_weights_name(settings, payload.base_model_id, db)
    hyper = payload.hyperparams
    name = (payload.name or f"papi-{payload.dataset_id[:8]}").strip()

    repo = JobRepository(db)
    job = repo.create(
        "train_prepare",
        {
            "dataset_id": payload.dataset_id,
            "base": base,
            "hyperparams": hyper.model_dump(),
        },
    )
    command = build_command(
        base=base,
        epochs=hyper.epochs,
        imgsz=hyper.imgsz,
        batch=hyper.batch,
        oversample=hyper.oversample,
        name=name,
    )
    manifest = {
        "dataset_id": payload.dataset_id,
        "dataset_name": dataset.name,
        "base_weights": base,
        "hyperparams": hyper.model_dump(),
        "augmentation": COLOUR_SAFE_AUG,
        "class_names": dataset.class_names_json,
        "command": command,
        "note": "Run on a CUDA GPU, then re-import best.pt via the Models page.",
    }
    root = dataset_root(settings, payload.dataset_id)
    try:
        bundle = build_training_bundle(settings, root, job.id, manifest)
    except Exception as exc:
        # Without this the job row stays 'queued' forever on a build failure (audit).
        repo.mark_failed(job.id, f"Training bundle build failed: {exc}")
        raise HTTPException(status_code=500, detail="Could not build the training bundle.") from exc
    repo.mark_succeeded(
        job.id,
        {"bundle": str(bundle), "command": command, "expecting_reimport": True},
    )
    return PrepareTrainingResponse(
        job_id=job.id,
        bundle_url=f"/api/training/{job.id}/bundle",
        command=command,
        manifest=manifest,
    )


@router.get("/training/{job_id}/bundle")
def download_training_bundle(
    job_id: str,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> FileResponse:
    settings = routes.get_settings()
    safe = job_id.replace("\\", "/").strip("/")
    if not safe or "/" in safe:
        raise HTTPException(status_code=404, detail="Not found")
    bundle = (settings.jobs_dir / safe / "bundle.zip").resolve()
    try:
        bundle.relative_to(settings.jobs_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    if not bundle.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        bundle, media_type="application/zip", filename=f"papi-training-{safe}.zip"
    )
