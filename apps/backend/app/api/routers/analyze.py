"""Upload + inference endpoints: ``/analyze``, ``/analyze-frame``,
``/analyze-frames`` and ``/analyze-sequence``.

Design note — monkeypatch seam: the integration tests replace the inference
singleton via ``monkeypatch.setattr("app.api.routes.get_inference_service", ...)``
and the security tests replace settings via
``monkeypatch.setattr("app.api.routes.get_settings", ...)``. Both patch the
``app.api.routes`` module namespace, so every request-time call here goes
through ``routes.get_inference_service()`` / ``routes.get_settings()`` (the
``routes`` module object) rather than a name imported into this module — that
is what makes the patches reach this handler. ``require_api_key`` is likewise
referenced as ``routes.require_api_key`` so its ``get_settings()`` lookup
resolves from the same patched namespace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.api._runways import validate_runway_id
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.services.media import detect_media_type, save_upload
from app.validation.analyze import parse_manual_drone_metadata
from app.validation.schemas import AnalysisPayload, FrameBatchPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@dataclass(frozen=True)
class AnalyzeParams:
    """Form fields shared by the three analyze endpoints.

    Kept in one dependency so the endpoint signatures stay in sync — each of
    /analyze, /analyze-frame and /analyze-frames previously repeated the same
    five-field block verbatim.
    """

    runway_id: str
    drone_id: str | None
    drone_latitude: float | None
    drone_longitude: float | None
    drone_altitude_m: float | None


def analyze_params(
    # Default to papi_24 (client-provided lamp altitude 461.37 m) rather than
    # papi_06 whose installation height is still unconfirmed by Intersoft
    # (audit B-CRIT-2 + open question carried forward). The frontend dropdown
    # still lets the user pick papi_06 explicitly.
    runway_id: Annotated[str, Form()] = "papi_24",
    drone_id: Annotated[str | None, Form()] = None,
    drone_latitude: Annotated[float | None, Form()] = None,
    drone_longitude: Annotated[float | None, Form()] = None,
    drone_altitude_m: Annotated[float | None, Form()] = None,
) -> AnalyzeParams:
    return AnalyzeParams(runway_id, drone_id, drone_latitude, drone_longitude, drone_altitude_m)


@router.post("/analyze", response_model=AnalysisPayload)
def analyze_media(
    file: Annotated[UploadFile, File()],
    params: Annotated[AnalyzeParams, Depends(analyze_params)],
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> AnalysisPayload:
    return _analyze_upload(file=file, params=params, db=db, image_only=False)


@router.post("/analyze-frame", response_model=AnalysisPayload)
def analyze_frame(
    file: Annotated[UploadFile, File()],
    params: Annotated[AnalyzeParams, Depends(analyze_params)],
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> AnalysisPayload:
    return _analyze_upload(file=file, params=params, db=db, image_only=True)


@router.post("/analyze-frames", response_model=FrameBatchPayload)
def analyze_frames(
    files: Annotated[list[UploadFile], File()],
    params: Annotated[AnalyzeParams, Depends(analyze_params)],
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> FrameBatchPayload:
    """Batch image analysis for the frontend folder-upload feature.

    Each file is analyzed in turn (sequentially, sharing the loaded inference model)
    and a single FrameBatchPayload aggregates the per-frame results plus total wall time.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image file.")

    # Bound the batch size so a 10,000-image folder upload can't pin the
    # worker for minutes (audit B-MAJ-5). Configurable via PAPI_MAX_BATCH_FRAMES.
    settings = routes.get_settings()
    if len(files) > settings.max_batch_frames:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Folder uploads are limited to {settings.max_batch_frames} frames per "
                f"request. Got {len(files)}. Split the folder and retry, or raise "
                f"PAPI_MAX_BATCH_FRAMES on the server."
            ),
        )

    # Reject an unknown runway once, up front, before any per-file disk I/O.
    validate_runway_id(params.runway_id)

    start = perf_counter()
    results: list[AnalysisPayload] = []
    for file in files:
        payload = _analyze_upload(file=file, params=params, db=db, image_only=True)
        results.append(payload)

    processing_ms = int((perf_counter() - start) * 1000)
    return FrameBatchPayload(
        frame_count=len(results),
        processing_ms=processing_ms,
        results=results,
    )


@router.post("/analyze-sequence", response_model=AnalysisPayload)
def analyze_sequence(
    files: Annotated[list[UploadFile], File()],
    params: Annotated[AnalyzeParams, Depends(analyze_params)],
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> AnalysisPayload:
    """Analyse an ordered folder of images as ONE video (folder->video feature).

    Unlike ``/analyze-frames`` (which returns a per-image batch), this treats the
    uploaded images as consecutive frames of a single clip: ByteTrack continuity,
    temporal red<->white transitions, and one annotated WebM artifact + aggregated
    verdict — the same pipeline as a real video upload. Files are ordered by
    filename so a drone's frame_000.jpg…frame_NNN.jpg sequence plays in capture order.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image file.")

    settings = routes.get_settings()
    if len(files) > settings.max_batch_frames:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image sequences are limited to {settings.max_batch_frames} frames per "
                f"request. Got {len(files)}. Split the folder and retry, or raise "
                f"PAPI_MAX_BATCH_FRAMES on the server."
            ),
        )

    validate_runway_id(params.runway_id)

    # Validate drone metadata BEFORE writing any upload to disk (same ordering as
    # _analyze_upload), so an invalid request can't leak saved files.
    manual_metadata = parse_manual_drone_metadata(
        params.drone_latitude, params.drone_longitude, params.drone_altitude_m
    )

    # Capture order: a folder upload arrives via webkitdirectory with names like
    # "flight/frame_000.jpg"; sort so the assembled clip plays in numeric capture order.
    ordered = sorted(files, key=lambda upload: upload.filename or "")
    first_name = ordered[0].filename or "sequence"
    folder = first_name.split("/")[0] if "/" in first_name else None
    display_name = f"{folder} ({len(ordered)} frames)" if folder else f"sequence ({len(ordered)} frames)"

    saved_paths: list = []
    try:
        for upload in ordered:
            if detect_media_type(upload.filename or "", upload.content_type) != "image":
                raise HTTPException(status_code=400, detail="Image sequences accept image files only.")
            saved_paths.append(save_upload(upload, settings))

        payload = routes.get_inference_service().analyze_frame_sequence(
            image_paths=saved_paths,
            runway_id=params.runway_id,
            original_filename=display_name,
            drone_id=params.drone_id,
            drone_metadata=manual_metadata,
        )
        log = AnalysisLogRepository(db).create_from_payload(payload)
        payload.log_id = log.id
        logger.info(
            "analysis.success",
            extra={
                "media_type": "video",
                "runway_id": params.runway_id,
                "global_state": payload.global_state,
                "confidence": payload.confidence,
                "processing_ms": payload.processing_ms,
                "log_id": log.id,
                "frame_count": payload.frame_count,
            },
        )
        return payload
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("analysis.value_error", extra={"runway_id": params.runway_id, "detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("analysis.error", extra={"runway_id": params.runway_id})
        raise HTTPException(
            status_code=503,
            detail="Inference service is temporarily unavailable. Check the server logs.",
        ) from exc
    finally:
        for path in saved_paths:
            path.unlink(missing_ok=True)


def _analyze_upload(
    file: UploadFile,
    params: AnalyzeParams,
    db: Session,
    image_only: bool,
) -> AnalysisPayload:
    settings = routes.get_settings()
    try:
        validate_runway_id(params.runway_id)
        media_type = detect_media_type(file.filename or "", file.content_type)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if image_only and media_type != "image":
        raise HTTPException(status_code=400, detail="Use /api/analyze-frame with image files only.")

    # Validate drone metadata BEFORE writing the upload to disk: parse_manual_drone_metadata
    # raises on invalid input, and if that happened after save_upload the just-saved file
    # leaked (it was created outside the try/finally that unlinks it). (audit backend-bugs)
    manual_metadata = parse_manual_drone_metadata(
        params.drone_latitude, params.drone_longitude, params.drone_altitude_m
    )
    saved_path = save_upload(file, settings)

    try:
        payload = routes.get_inference_service().analyze(
            media_path=saved_path,
            media_type=media_type,
            runway_id=params.runway_id,
            original_filename=file.filename or saved_path.name,
            drone_id=params.drone_id,
            drone_metadata=manual_metadata,
        )
        log = AnalysisLogRepository(db).create_from_payload(payload)
        payload.log_id = log.id
        # Structured success log — pairs with the request_id from middleware
        # so a single analysis can be traced end-to-end (audit B-IMP-4).
        logger.info(
            "analysis.success",
            extra={
                "media_type": media_type,
                "runway_id": params.runway_id,
                "global_state": payload.global_state,
                "confidence": payload.confidence,
                "processing_ms": payload.processing_ms,
                "log_id": log.id,
            },
        )
        return payload
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("analysis.value_error", extra={"runway_id": params.runway_id, "detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        # Any other failure — RuntimeError (missing model/OpenCV), cv2.error, or a
        # SQLAlchemyError on commit — is logged server-side and returned as a generic
        # 503 so internal paths/library internals are never disclosed (rubric LR1D).
        # Previously only RuntimeError was caught, so cv2/DB errors surfaced as an
        # opaque 500 with no structured log (audit backend-bugs).
        logger.exception("analysis.error", extra={"runway_id": params.runway_id})
        raise HTTPException(
            status_code=503,
            detail="Inference service is temporarily unavailable. Check the server logs.",
        ) from exc
    finally:
        saved_path.unlink(missing_ok=True)
