"""Dataset management + assisted-labeling endpoints (api-key gated)."""

from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.database import get_session
from app.models.dataset import Dataset
from app.repositories.datasets import DatasetRepository
from app.repositories.model_registry import ModelRegistryRepository
from app.services.dataset_bundle import ingest_bundle, is_zip
from app.services.datasets import (
    CANDIDATES_DIR,
    DEFAULT_CLASS_NAMES,
    IMAGE_SUFFIXES,
    STAGING_SPLIT,
    dataset_root,
    ensure_dataset_dirs,
    format_yolo_label,
    refresh_counts,
    split_for_name,
    write_data_yaml,
    write_split_files,
)
from app.services.jobs import get_job_runner
from app.services.media import detect_media_type, validate_media_signature
from app.services.upload_limits import enforce_upload_collection_limits, upload_size_bytes
from app.validation.schemas import (
    CandidateBox,
    CandidateImage,
    CandidatesResponse,
    CommitRequest,
    CommitResponse,
    DatasetResponse,
)

router = APIRouter(prefix="/api")

_MEDIA_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else value.isoformat()


def _to_response(dataset: Dataset) -> DatasetResponse:
    class_names = None
    if isinstance(dataset.class_names_json, dict):
        try:
            class_names = {int(k): str(v) for k, v in dataset.class_names_json.items()}
        except (TypeError, ValueError):
            class_names = None
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        source=dataset.source,
        status=dataset.status,
        class_names=class_names,
        n_train=dataset.n_train,
        n_val=dataset.n_val,
        n_test=dataset.n_test,
        created_at=_iso(dataset.created_at),
    )


def _stream_save(upload: UploadFile, target: Path, max_bytes: int, what: str) -> None:
    written = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"{what} exceeds the upload size limit.")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _cleanup_dataset(repo: DatasetRepository, dataset_id: str, root: Path) -> None:
    """Best-effort removal for a dataset row plus its filesystem tree."""
    try:
        repo.db.rollback()
    except Exception:  # noqa: BLE001 - cleanup should still remove files
        pass
    try:
        repo.delete(dataset_id)
    except KeyError:
        pass
    shutil.rmtree(root, ignore_errors=True)


@router.get("/datasets", response_model=list[DatasetResponse])
def list_datasets(
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> list[DatasetResponse]:
    return [_to_response(d) for d in DatasetRepository(db).list_all()]


@router.post("/datasets", response_model=DatasetResponse, status_code=status.HTTP_201_CREATED)
def upload_dataset_bundle(
    file: UploadFile,
    name: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> DatasetResponse:
    """Upload a prepared labelled YOLO dataset (zip) and register it as ready."""
    settings = routes.get_settings()
    if not (name or "").strip():
        raise HTTPException(status_code=400, detail="A dataset name is required.")
    # Peek the signature before writing.
    try:
        position = file.file.tell()
        header = file.file.read(8)
        file.file.seek(position)
    except (AttributeError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Could not read the uploaded file.") from exc
    if not is_zip(header):
        raise HTTPException(status_code=400, detail="Dataset bundle must be a .zip archive.")

    dataset = DatasetRepository(db).create(
        name=name.strip(), source="bundle", status="draft", storage_path=""
    )
    tmp_zip = settings.tmp_dir / f"{uuid4().hex}.zip"
    max_bytes = settings.max_dataset_upload_mb * 1024 * 1024
    max_extract_bytes = settings.max_dataset_extract_mb * 1024 * 1024
    root = dataset_root(settings, dataset.id)
    try:
        root.mkdir(parents=True, exist_ok=True)
        _stream_save(file, tmp_zip, max_bytes, "Dataset bundle")
        result = ingest_bundle(tmp_zip, root, max_extract_bytes=max_extract_bytes)
    except Exception as exc:
        # Any failure (size cap / malformed zip / extraction error) must clean up the
        # just-created draft row + directory rather than leaking them. Bad input is a
        # 400; an unexpected error re-raises as a 500 (with the row still cleaned up).
        _cleanup_dataset(DatasetRepository(db), dataset.id, root)
        if isinstance(exc, (ValueError, zipfile.BadZipFile)):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise
    finally:
        tmp_zip.unlink(missing_ok=True)

    repo = DatasetRepository(db)
    repo.set_class_names(dataset.id, result["class_names"])
    dataset = repo.update_counts(
        dataset.id,
        n_train=result["n_train"],
        n_val=result["n_val"],
        n_test=result["n_test"],
        data_yaml_path=result["data_yaml"],
        status="ready",
    )
    # storage_path was empty at create; persist it now.
    dataset.storage_path = str(root)
    db.commit()
    db.refresh(dataset)
    return _to_response(dataset)


@router.post("/datasets/assisted", status_code=status.HTTP_201_CREATED)
def start_assisted_labeling(
    files: list[UploadFile],
    name: Annotated[str, Form()],
    model_id: Annotated[str, Form()],
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> dict:
    """Upload raw images and launch a model-assisted labeling job.

    The chosen model pre-annotates the images; the operator then reviews/corrects
    the candidate boxes (GET /candidates) and commits them (POST /commit).
    """
    settings = routes.get_settings()
    if not (name or "").strip():
        raise HTTPException(status_code=400, detail="A dataset name is required.")
    enforce_upload_collection_limits(
        files, settings, what="Assisted-label uploads", count_unit="images"
    )
    model_row = ModelRegistryRepository(db).get(model_id)
    if model_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}")

    # The dataset's classes come from the labeling model so candidate class ids line up.
    class_names = DEFAULT_CLASS_NAMES
    if isinstance(model_row.classes_json, dict):
        try:
            class_names = {int(k): str(v) for k, v in model_row.classes_json.items()}
        except (TypeError, ValueError):
            class_names = DEFAULT_CLASS_NAMES

    for upload in files:
        if upload_size_bytes(upload) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"Each assisted-label image is limited to {settings.max_upload_mb} MB.",
            )
        try:
            media_type = detect_media_type(upload.filename or "", upload.content_type)
            if media_type != "image":
                raise ValueError("Assisted labeling accepts image files only.")
            validate_media_signature(upload, "image")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = DatasetRepository(db)
    dataset = repo.create(
        name=name.strip(), source="assisted", status="labeling", storage_path="", class_names=class_names
    )
    root = dataset_root(settings, dataset.id)
    try:
        ensure_dataset_dirs(root, staging=True)
        staging = root / "images" / STAGING_SPLIT
        max_bytes = settings.max_upload_mb * 1024 * 1024
        saved = 0
        for upload in files:
            dest = _unique_staged_name(staging, upload.filename or f"frame_{saved}.jpg")
            _stream_save(upload, dest, max_bytes, "Image")
            saved += 1
        if saved == 0:
            raise HTTPException(status_code=400, detail="No valid images were uploaded.")

        dataset.storage_path = str(root)
        db.commit()
        job_id = get_job_runner().submit(
            "label_assist", {"dataset_id": dataset.id, "model_id": model_id}
        )
        return {"dataset_id": dataset.id, "job_id": job_id, "n_images": saved}
    except HTTPException:
        _cleanup_dataset(repo, dataset.id, root)
        raise
    except Exception:
        _cleanup_dataset(repo, dataset.id, root)
        raise


def _unique_staged_name(staging: Path, filename: str) -> Path:
    safe = Path(filename).name.replace("\\", "/").split("/")[-1] or "frame.jpg"
    suffix = Path(safe).suffix.lower() or ".jpg"
    if suffix not in IMAGE_SUFFIXES:
        suffix = ".jpg"
    stem = Path(safe).stem or "frame"
    candidate = staging / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    return staging / f"{stem}_{uuid4().hex[:6]}{suffix}"


@router.get("/datasets/{dataset_id}/candidates", response_model=CandidatesResponse)
def get_candidates(
    dataset_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> CandidatesResponse:
    settings = routes.get_settings()
    dataset = DatasetRepository(db).get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Unknown dataset.")
    root = dataset_root(settings, dataset_id)
    staging = root / "images" / STAGING_SPLIT
    candidates_dir = root / "labels" / CANDIDATES_DIR
    images: list[CandidateImage] = []
    if staging.is_dir():
        for image in sorted(staging.iterdir()):
            if image.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            boxes = _read_candidate_boxes(candidates_dir / f"{image.stem}.txt")
            images.append(
                CandidateImage(
                    image_id=image.stem,
                    image_url=f"/api/datasets/{dataset_id}/staged/{image.name}",
                    boxes=boxes,
                )
            )
    return CandidatesResponse(
        dataset_id=dataset_id, status=dataset.status, total=len(images), images=images
    )


def _read_candidate_boxes(path: Path) -> list[CandidateBox]:
    if not path.is_file():
        return []
    boxes: list[CandidateBox] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            class_id = int(float(parts[0]))
            cx, cy, bw, bh = (float(p) for p in parts[1:5])
            conf = float(parts[5]) if len(parts) >= 6 else None
        except ValueError:
            continue
        boxes.append(CandidateBox(class_id=class_id, x=cx, y=cy, w=bw, h=bh, conf=conf))
    return boxes


@router.get("/datasets/{dataset_id}/staged/{filename}")
def get_staged_image(
    dataset_id: str,
    filename: str,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> FileResponse:
    settings = routes.get_settings()
    try:
        root = dataset_root(settings, dataset_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    staging = (root / "images" / STAGING_SPLIT).resolve()
    target = (staging / filename).resolve()
    try:
        target.relative_to(staging)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    if not target.is_file() or target.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=404, detail="Not found")
    media_type = _MEDIA_CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=media_type)


@router.post("/datasets/{dataset_id}/commit", response_model=CommitResponse)
def commit_labels(
    dataset_id: str,
    payload: CommitRequest,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> CommitResponse:
    """Write reviewed/corrected labels into the dataset splits and mark it ready."""
    settings = routes.get_settings()
    repo = DatasetRepository(db)
    dataset = repo.get(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Unknown dataset.")
    root = dataset_root(settings, dataset_id)
    staging = root / "images" / STAGING_SPLIT
    candidates_dir = root / "labels" / CANDIDATES_DIR
    ensure_dataset_dirs(root)

    class_names = DEFAULT_CLASS_NAMES
    if isinstance(dataset.class_names_json, dict):
        try:
            class_names = {int(k): str(v) for k, v in dataset.class_names_json.items()}
        except (TypeError, ValueError):
            class_names = DEFAULT_CLASS_NAMES
    n_classes = len(class_names)

    committed = 0
    for item in payload.images:
        source = _find_staged(staging, item.image_id)
        if source is None:
            continue
        if item.skip:
            source.unlink(missing_ok=True)
            (candidates_dir / f"{source.stem}.txt").unlink(missing_ok=True)
            continue
        for box in item.boxes:
            if not (0 <= box.class_id < n_classes):
                raise HTTPException(
                    status_code=400,
                    detail=f"Box class_id {box.class_id} out of range for {n_classes} classes.",
                )
        split = split_for_name(source.name)
        dest_image = root / "images" / split / source.name
        shutil.move(str(source), str(dest_image))
        label_text = format_yolo_label([(b.class_id, b.x, b.y, b.w, b.h) for b in item.boxes])
        (root / "labels" / split / f"{source.stem}.txt").write_text(label_text, encoding="utf-8")
        (candidates_dir / f"{source.stem}.txt").unlink(missing_ok=True)
        committed += 1

    write_split_files(root)
    yaml_path = write_data_yaml(root, class_names)
    n_train, n_val, n_test = refresh_counts(root)
    new_status = "ready" if (n_train + n_val + n_test) > 0 else "labeling"
    # Once every staged image has been committed or skipped, drop the now-empty
    # staging + candidates scratch so it doesn't linger on the datasets volume.
    # Kept when images remain (a partial-commit round leaves the rest for review).
    if staging.is_dir() and not any(p.suffix.lower() in IMAGE_SUFFIXES for p in staging.iterdir()):
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(candidates_dir, ignore_errors=True)
    repo.update_counts(
        dataset_id,
        n_train=n_train,
        n_val=n_val,
        n_test=n_test,
        data_yaml_path=str(yaml_path),
        status=new_status,
    )
    return CommitResponse(dataset_id=dataset_id, n_committed=committed, status=new_status)


def _find_staged(staging: Path, image_id: str) -> Path | None:
    if not staging.is_dir():
        return None
    # image_id is a filename stem; guard against traversal.
    safe = Path(image_id).name
    if safe != image_id or safe in ("", ".", ".."):
        return None
    for suffix in IMAGE_SUFFIXES:
        candidate = staging / f"{safe}{suffix}"
        if candidate.is_file():
            return candidate
    return None


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> Response:
    settings = routes.get_settings()
    repo = DatasetRepository(db)
    try:
        repo.delete(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown dataset.") from exc
    try:
        root = dataset_root(settings, dataset_id)
        shutil.rmtree(root, ignore_errors=True)
    except ValueError:
        pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)
