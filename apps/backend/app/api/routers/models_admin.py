"""Model-management endpoints (operator-auth gated).

Upload, promote-to-default, disable/enable, delete, and enqueue evaluation. Reads
stay on ``meta.py`` (``GET /api/model``, ``/api/models``); everything here mutates
the registry or launches work, so each carries ``require_api_key``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.api.routers.jobs import job_to_response
from app.database import get_session
from app.repositories.datasets import DatasetRepository
from app.repositories.jobs import JobRepository
from app.repositories.model_registry import (
    DefaultModelError,
    ModelRegistryRepository,
    ProtectedModelError,
)
from app.services.datasets import count_images, dataset_root
from app.services.jobs import get_job_runner
from app.services.model_upload import (
    register_model_from_path,
    save_model_upload,
    validate_model_signature,
)
from app.validation.schemas import EvaluateRequest, JobResponse, ModelInfo

router = APIRouter(prefix="/api")

_VALID_ROLES = ("detector", "transition")


def _model_info_from_row(row, settings) -> ModelInfo:
    """Build a ModelInfo for a committed registry row WITHOUT relying on the in-memory
    registry — the last-resort upload-response fallback when a post-insert reload
    failed, so a successful upload is never reported as a 500.

    Delegates to the single shared builder (via ``registry_from_rows`` ->
    ``model_info_for_entry``) so it can never drift from GET /api/models. Only the
    forced default flag is corrected: ``registry_from_rows`` makes a lone row the
    default, but the row's real ``is_default`` is authoritative here.
    """
    from dataclasses import replace

    from app.services.model_registry import registry_from_rows

    entry = registry_from_rows([row], settings).get(row.id)
    entry = replace(entry, default=bool(row.is_default))
    return routes.get_inference_service().model_info_for_entry(entry)


@router.post("/models", response_model=ModelInfo, status_code=status.HTTP_201_CREATED)
def upload_model(
    file: UploadFile,
    # Bound the free-text fields: label maps to String(160), so an unbounded value
    # would 500 on Postgres at commit instead of returning a clean 422 here (audit #18).
    label: Annotated[str, Form(max_length=160)],
    role: Annotated[str, Form(max_length=32)] = "detector",
    description: Annotated[str | None, Form(max_length=2000)] = None,
    make_default: Annotated[bool, Form()] = False,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> ModelInfo:
    """Upload a .pt/.onnx model and register it.

    SECURITY: a .pt is a pickle; loading it executes code. This endpoint is
    auth gated for exactly that reason: only a trusted operator can reach it.
    """
    settings = routes.get_settings()
    normalized_role = (role or "detector").strip().lower()
    if normalized_role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="role must be 'detector' or 'transition'.")
    if not (label or "").strip():
        raise HTTPException(status_code=400, detail="A model label is required.")

    try:
        validate_model_signature(file)
        saved = save_model_upload(file, settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        row = register_model_from_path(
            settings,
            saved,
            label=label.strip(),
            role=normalized_role,
            description=(description or None),
            source="uploaded",
            make_default=make_default,
        )
    except (RuntimeError, ValueError) as exc:
        saved.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # The model is committed. Report it from the (reloaded) registry; if the
    # post-insert reload transiently failed, force one more reload, and as a last
    # resort describe it from the committed row — a successful upload must never 500.
    service = routes.get_inference_service()
    try:
        return service.model_info(row.id)
    except ValueError:
        service.reload_registry()
        try:
            return service.model_info(row.id)
        except ValueError:
            return _model_info_from_row(row, settings)


@router.post("/models/{model_id}/promote", response_model=ModelInfo)
def promote_model(
    model_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> ModelInfo:
    try:
        ModelRegistryRepository(db).set_default(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    service = routes.get_inference_service()
    service.reload_registry()
    return service.model_info(model_id)


@router.post("/models/{model_id}/disable", response_model=ModelInfo)
def disable_model(
    model_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> ModelInfo:
    try:
        ModelRegistryRepository(db).disable(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}") from exc
    except DefaultModelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    service = routes.get_inference_service()
    service.reload_registry()
    return service.model_info(model_id)


@router.post("/models/{model_id}/enable", response_model=ModelInfo)
def enable_model(
    model_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> ModelInfo:
    try:
        ModelRegistryRepository(db).enable(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}") from exc
    service = routes.get_inference_service()
    service.reload_registry()
    return service.model_info(model_id)


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> Response:
    settings = routes.get_settings()
    repo = ModelRegistryRepository(db)
    try:
        row = repo.delete(model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}") from exc
    except ProtectedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DefaultModelError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # Best-effort weights cleanup for uploaded/trained models stored under the
    # writable user-models dir. Built-in (repo-tracked) weights are never deleted.
    if row.source in ("uploaded", "trained"):
        try:
            weights = Path(row.storage_path).resolve()
            weights.relative_to(settings.user_models_dir.resolve())
            weights.unlink(missing_ok=True)
        except (ValueError, OSError):
            pass

    routes.get_inference_service().reload_registry()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/models/{model_id}/evaluate", response_model=JobResponse)
def evaluate_model(
    model_id: str,
    payload: EvaluateRequest,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> JobResponse:
    if ModelRegistryRepository(db).get(model_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}")
    dataset = DatasetRepository(db).get(payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Unknown dataset.")
    if dataset.status != "ready":
        raise HTTPException(status_code=400, detail="Dataset is not ready for evaluation.")
    # A row can be 'ready' in the DB while its files are absent on THIS node (e.g. a
    # built-in seeded into a shared DB whose data landed elsewhere, or an unmounted
    # datasets volume). Reject up front with an actionable message rather than
    # enqueuing a job that dies with the opaque "no data.yaml" handler error.
    settings = routes.get_settings()
    root = dataset_root(settings, payload.dataset_id)
    if not (root / "data.yaml").is_file():
        raise HTTPException(
            status_code=400,
            detail="Dataset files are not available on this server (no data.yaml). "
            "Restart/redeploy the backend to re-seed built-ins, or re-upload the dataset.",
        )
    if count_images(root, payload.split) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Dataset has no images in the '{payload.split}' split to evaluate.",
        )
    job_id = get_job_runner().submit(
        "evaluate",
        {"model_id": model_id, "dataset_id": payload.dataset_id, "split": payload.split},
    )
    job = JobRepository(db).get(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Job was not created.")
    return job_to_response(job)
