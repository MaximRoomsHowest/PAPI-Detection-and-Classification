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
import re
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.api._runways import validate_runway_id
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.services.media import detect_media_type, save_upload, validate_media_signature
from app.services.telemetry import DroneSample, parse_telemetry
from app.validation.analyze import parse_manual_drone_metadata
from app.validation.schemas import AnalysisPayload, FrameBatchPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_NATURAL_PART_RE = re.compile(r"(\d+)")


def _natural_upload_key(upload: UploadFile) -> tuple[tuple[int, int | str], ...]:
    """Sort folder frames by numeric capture order, not plain lexicographic order."""
    filename = upload.filename or ""
    return tuple(
        # Cap the digit-run length: int() on a >4300-digit string raises ValueError
        # under Python 3.11+ (int-str conversion limit), which would 500 the upload.
        # Real frame numbers are short; longer runs fall back to string sort (audit).
        (1, int(part)) if part.isdigit() and len(part) <= 18 else (0, part.casefold())
        for part in _NATURAL_PART_RE.split(filename)
    )


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
    # "tracking" (temporal red<->white flips) or "model" (learned class-2 events from the 3-class
    # detector). None lets the service apply its configured default. Validated server-side; an
    # unknown value falls back to "tracking".
    transition_method: str | None


def analyze_params(
    # Default to papi_24: its 461.37 m reference was validated against the client's
    # angle tool. papi_06 is selectable and uses the data_analysis-branch 461.37 m
    # reference; its client image/MRK metadata is present, but commissioned
    # set-angles/lamp-order mapping are still not bound into runtime config.
    runway_id: Annotated[str, Form()] = "papi_24",
    drone_id: Annotated[str | None, Form()] = None,
    drone_latitude: Annotated[float | None, Form()] = None,
    drone_longitude: Annotated[float | None, Form()] = None,
    drone_altitude_m: Annotated[float | None, Form()] = None,
    transition_method: Annotated[str | None, Form()] = None,
) -> AnalyzeParams:
    return AnalyzeParams(
        runway_id, drone_id, drone_latitude, drone_longitude, drone_altitude_m, transition_method
    )


def read_metadata_samples(metadata_file: UploadFile | None) -> list[DroneSample] | None:
    """Parse an optional uploaded telemetry file (DJI .SRT / CSV / JSON) into drone fixes.

    Returns ``None`` when no file (or an empty file) was sent, so the angle calc falls
    back to the manual fix / embedded EXIF. A file that can't be parsed into any usable
    fix raises 400 (``parse_telemetry`` raises ``ValueError``) — surfaced to the user
    instead of silently degrading to angle-unavailable. Read here, before any media is
    written to disk, so a bad telemetry file can't leak a saved upload.
    """
    if metadata_file is None:
        return None
    settings = routes.get_settings()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    try:
        raw = metadata_file.file.read(max_bytes + 1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Could not read the telemetry file.") from exc
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Telemetry file exceeds the {settings.max_upload_mb} MB limit.",
        )
    if not raw or not raw.strip():
        return None
    try:
        return parse_telemetry(metadata_file.filename or "", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _upload_size_bytes(upload: UploadFile) -> int:
    """Return the spooled upload size without changing the caller's read position."""
    try:
        position = upload.file.tell()
        upload.file.seek(0, 2)
        size = upload.file.tell()
    except (AttributeError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Could not inspect uploaded file size.") from exc
    finally:
        try:
            upload.file.seek(position)
        except (NameError, AttributeError, OSError, ValueError):
            pass
    return size


def _enforce_batch_upload_budget(files: list[UploadFile], settings) -> None:
    max_bytes = settings.max_batch_upload_mb * 1024 * 1024
    total = 0
    for upload in files:
        total += _upload_size_bytes(upload)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Folder uploads are limited to {settings.max_batch_upload_mb} MB "
                    f"total per request. Split the folder and retry, or raise "
                    f"PAPI_MAX_BATCH_UPLOAD_MB on the server."
                ),
            )


def _validate_batch_upload(files: list[UploadFile], *, what: str):
    """Shared front-door checks for the two batch endpoints; returns the settings.

    Rejects an empty upload (400) and a batch over PAPI_MAX_BATCH_FRAMES (413) so a
    10,000-image folder can't pin the worker for minutes (audit B-MAJ-5), then runs
    the byte-budget guard. ``what`` names the upload in the 413 message ("Folder
    uploads" / "Image sequences").
    """
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image file.")
    settings = routes.get_settings()
    if len(files) > settings.max_batch_frames:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{what} are limited to {settings.max_batch_frames} frames per "
                f"request. Got {len(files)}. Split the folder and retry, or raise "
                f"PAPI_MAX_BATCH_FRAMES on the server."
            ),
        )
    _enforce_batch_upload_budget(files, settings)
    return settings


@contextmanager
def _analysis_error_handling(runway_id: str):
    """Map inference failures to the analyze endpoints' HTTP contract.

    A ``ValueError`` (bad upload / unreadable media / telemetry) becomes a 400; any
    other failure — RuntimeError (missing model/OpenCV), cv2.error, or a
    SQLAlchemyError on commit — is logged server-side and returned as a generic 503
    so internal paths/library internals are never disclosed (rubric LR1D). An
    already-formed HTTPException passes through unchanged. The success-path file
    cleanup stays in each caller's own ``finally`` (the saved-file set differs).
    """
    try:
        yield
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("analysis.value_error", extra={"runway_id": runway_id, "detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("analysis.error", extra={"runway_id": runway_id})
        raise HTTPException(
            status_code=503,
            detail="Inference service is temporarily unavailable. Check the server logs.",
        ) from exc


def _log_analysis_success(
    media_type: str,
    runway_id: str,
    payload: AnalysisPayload,
    log_id: str,
    *,
    include_frame_count: bool = False,
) -> None:
    """Structured success log shared by the upload and sequence paths.

    Pairs with the request_id from middleware so a single analysis can be traced
    end-to-end (audit B-IMP-4). The sequence path passes ``include_frame_count`` so
    the assembled-clip frame total is recorded.
    """
    extra = {
        "media_type": media_type,
        "runway_id": runway_id,
        "global_state": payload.global_state,
        "confidence": payload.confidence,
        "processing_ms": payload.processing_ms,
        "log_id": log_id,
    }
    if include_frame_count:
        extra["frame_count"] = payload.frame_count
    logger.info("analysis.success", extra=extra)


@router.post("/analyze", response_model=AnalysisPayload)
def analyze_media(
    file: Annotated[UploadFile, File()],
    metadata_file: Annotated[UploadFile | None, File()] = None,
    params: Annotated[AnalyzeParams, Depends(analyze_params)] = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> AnalysisPayload:
    drone_samples = read_metadata_samples(metadata_file)
    return _analyze_upload(file=file, params=params, db=db, image_only=False, drone_samples=drone_samples)


@router.post("/analyze-frame", response_model=AnalysisPayload)
def analyze_frame(
    file: Annotated[UploadFile, File()],
    metadata_file: Annotated[UploadFile | None, File()] = None,
    params: Annotated[AnalyzeParams, Depends(analyze_params)] = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> AnalysisPayload:
    drone_samples = read_metadata_samples(metadata_file)
    return _analyze_upload(file=file, params=params, db=db, image_only=True, drone_samples=drone_samples)


@router.post("/analyze-frames", response_model=FrameBatchPayload)
def analyze_frames(
    files: Annotated[list[UploadFile], File()],
    metadata_file: Annotated[UploadFile | None, File()] = None,
    params: Annotated[AnalyzeParams, Depends(analyze_params)] = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> FrameBatchPayload:
    """Batch image analysis for the frontend folder-upload feature.

    Each file is analyzed in turn (sequentially, sharing the loaded inference model)
    and a single FrameBatchPayload aggregates the per-frame results plus total wall time.
    """
    _validate_batch_upload(files, what="Folder uploads")

    # Reject an unknown runway once, up front, before any per-file disk I/O.
    validate_runway_id(params.runway_id)

    # Parse the optional telemetry file once; the same representative fix applies to
    # every image in the batch (each frame is analysed independently as a still).
    drone_samples = read_metadata_samples(metadata_file)

    start = perf_counter()
    results: list[AnalysisPayload] = []
    for file in files:
        payload = _analyze_upload(file=file, params=params, db=db, image_only=True, drone_samples=drone_samples)
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
    metadata_file: Annotated[UploadFile | None, File()] = None,
    params: Annotated[AnalyzeParams, Depends(analyze_params)] = None,
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
    settings = _validate_batch_upload(files, what="Image sequences")

    validate_runway_id(params.runway_id)

    # Validate drone metadata BEFORE writing any upload to disk (same ordering as
    # _analyze_upload), so an invalid request can't leak saved files. A telemetry
    # file (when supplied) drives a real per-frame angle track for the assembled clip.
    manual_metadata = parse_manual_drone_metadata(
        params.drone_latitude, params.drone_longitude, params.drone_altitude_m
    )
    drone_samples = read_metadata_samples(metadata_file)

    # Capture order: a folder upload arrives via webkitdirectory with names like
    # "flight/frame_000.jpg"; natural-sort so frame_10 never plays before frame_2.
    ordered = sorted(files, key=_natural_upload_key)
    first_name = ordered[0].filename or "sequence"
    folder = first_name.split("/")[0] if "/" in first_name else None
    display_name = f"{folder} ({len(ordered)} frames)" if folder else f"sequence ({len(ordered)} frames)"

    saved_paths: list = []
    try:
        with _analysis_error_handling(params.runway_id):
            for upload in ordered:
                media_type = detect_media_type(upload.filename or "", upload.content_type)
                if media_type != "image":
                    raise HTTPException(status_code=400, detail="Image sequences accept image files only.")
                validate_media_signature(upload, media_type)
                saved_paths.append(save_upload(upload, settings))

            payload = routes.get_inference_service().analyze_frame_sequence(
                image_paths=saved_paths,
                runway_id=params.runway_id,
                original_filename=display_name,
                drone_id=params.drone_id,
                drone_metadata=manual_metadata,
                drone_samples=drone_samples,
                transition_method=params.transition_method,
            )
            log = AnalysisLogRepository(db).create_from_payload(payload)
            payload.log_id = log.id
            _log_analysis_success(
                "video", params.runway_id, payload, log.id, include_frame_count=True
            )
            return payload
    finally:
        for path in saved_paths:
            path.unlink(missing_ok=True)


def _analyze_upload(
    file: UploadFile,
    params: AnalyzeParams,
    db: Session,
    image_only: bool,
    drone_samples: list[DroneSample] | None = None,
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
    try:
        validate_media_signature(file, media_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Validate drone metadata BEFORE writing the upload to disk: parse_manual_drone_metadata
    # raises on invalid input, and if that happened after save_upload the just-saved file
    # leaked (it was created outside the try/finally that unlinks it). (audit backend-bugs)
    manual_metadata = parse_manual_drone_metadata(
        params.drone_latitude, params.drone_longitude, params.drone_altitude_m
    )
    saved_path = save_upload(file, settings)

    try:
        with _analysis_error_handling(params.runway_id):
            payload = routes.get_inference_service().analyze(
                media_path=saved_path,
                media_type=media_type,
                runway_id=params.runway_id,
                original_filename=file.filename or saved_path.name,
                drone_id=params.drone_id,
                drone_metadata=manual_metadata,
                drone_samples=drone_samples,
                transition_method=params.transition_method,
            )
            log = AnalysisLogRepository(db).create_from_payload(payload)
            payload.log_id = log.id
            _log_analysis_success(media_type, params.runway_id, payload, log.id)
            return payload
    finally:
        saved_path.unlink(missing_ok=True)
