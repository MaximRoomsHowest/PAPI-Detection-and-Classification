import csv
import hmac
import io
import logging
import os
from datetime import datetime
from time import perf_counter
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.services.inference import get_inference_service
from app.services.media import detect_media_type, save_upload
from app.services.runways import get_runway, list_runways
from app.validation.analyze import parse_manual_drone_metadata
from app.validation.schemas import (
    AnalysisPayload,
    FrameBatchPayload,
    InferenceStats,
    LogListItem,
    ModelInfo,
    RunwayResponse,
    SystemInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    settings = get_settings()
    # Constant-time comparison so a timing side-channel can't recover the key
    # character-by-character (audit IMP-BE-9 / IMP-SEC-1).
    if settings.api_key and not (x_api_key and hmac.compare_digest(x_api_key, settings.api_key)):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


@router.post("/analyze", response_model=AnalysisPayload)
async def analyze_media(
    file: Annotated[UploadFile, File()],
    # Default to papi_24 (client-provided lamp altitude 461.37 m) rather than
    # papi_06 whose installation height is still unconfirmed by Intersoft
    # (audit B-CRIT-2 + open question carried forward). Frontend dropdown
    # still lets the user pick papi_06 explicitly.
    runway_id: Annotated[str, Form()] = "papi_24",
    drone_id: Annotated[str | None, Form()] = None,
    drone_latitude: Annotated[float | None, Form()] = None,
    drone_longitude: Annotated[float | None, Form()] = None,
    drone_altitude_m: Annotated[float | None, Form()] = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> AnalysisPayload:
    return await _analyze_upload(
        file=file,
        runway_id=runway_id,
        drone_id=drone_id,
        drone_latitude=drone_latitude,
        drone_longitude=drone_longitude,
        drone_altitude_m=drone_altitude_m,
        db=db,
        image_only=False,
    )


@router.post("/analyze-frame", response_model=AnalysisPayload)
async def analyze_frame(
    file: Annotated[UploadFile, File()],
    # Default to papi_24 (client-provided lamp altitude 461.37 m) rather than
    # papi_06 whose installation height is still unconfirmed by Intersoft
    # (audit B-CRIT-2 + open question carried forward). Frontend dropdown
    # still lets the user pick papi_06 explicitly.
    runway_id: Annotated[str, Form()] = "papi_24",
    drone_id: Annotated[str | None, Form()] = None,
    drone_latitude: Annotated[float | None, Form()] = None,
    drone_longitude: Annotated[float | None, Form()] = None,
    drone_altitude_m: Annotated[float | None, Form()] = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> AnalysisPayload:
    return await _analyze_upload(
        file=file,
        runway_id=runway_id,
        drone_id=drone_id,
        drone_latitude=drone_latitude,
        drone_longitude=drone_longitude,
        drone_altitude_m=drone_altitude_m,
        db=db,
        image_only=True,
    )


@router.post("/analyze-frames", response_model=FrameBatchPayload)
async def analyze_frames(
    files: Annotated[list[UploadFile], File()],
    # Default to papi_24 (client-provided lamp altitude 461.37 m) rather than
    # papi_06 whose installation height is still unconfirmed by Intersoft
    # (audit B-CRIT-2 + open question carried forward). Frontend dropdown
    # still lets the user pick papi_06 explicitly.
    runway_id: Annotated[str, Form()] = "papi_24",
    drone_id: Annotated[str | None, Form()] = None,
    drone_latitude: Annotated[float | None, Form()] = None,
    drone_longitude: Annotated[float | None, Form()] = None,
    drone_altitude_m: Annotated[float | None, Form()] = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> FrameBatchPayload:
    """Batch image analysis for the frontend folder-upload feature.

    Each file is analyzed in turn (sequentially, sharing the loaded inference model)
    and a single FrameBatchPayload aggregates the per-frame results plus total wall time.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image file.")

    # Bound the batch size so a 10,000-image folder upload can't pin the
    # worker for minutes (audit B-MAJ-5). Configurable via PAPI_MAX_BATCH_FRAMES.
    settings = get_settings()
    if len(files) > settings.max_batch_frames:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Folder uploads are limited to {settings.max_batch_frames} frames per "
                f"request. Got {len(files)}. Split the folder and retry, or raise "
                f"PAPI_MAX_BATCH_FRAMES on the server."
            ),
        )

    start = perf_counter()
    results: list[AnalysisPayload] = []
    for file in files:
        payload = await _analyze_upload(
            file=file,
            runway_id=runway_id,
            drone_id=drone_id,
            drone_latitude=drone_latitude,
            drone_longitude=drone_longitude,
            drone_altitude_m=drone_altitude_m,
            db=db,
            image_only=True,
        )
        results.append(payload)

    processing_ms = int((perf_counter() - start) * 1000)
    return FrameBatchPayload(
        frame_count=len(results),
        processing_ms=processing_ms,
        results=results,
    )


async def _analyze_upload(
    file: UploadFile,
    runway_id: str,
    drone_id: str | None,
    drone_latitude: float | None,
    drone_longitude: float | None,
    drone_altitude_m: float | None,
    db: Session,
    image_only: bool,
) -> AnalysisPayload:
    settings = get_settings()
    try:
        get_runway(runway_id)
        media_type = detect_media_type(file.filename or "", file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if image_only and media_type != "image":
        raise HTTPException(status_code=400, detail="Use /api/analyze-frame with image files only.")

    saved_path = await save_upload(file, settings)
    manual_metadata = parse_manual_drone_metadata(drone_latitude, drone_longitude, drone_altitude_m)

    try:
        payload = get_inference_service().analyze(
            media_path=saved_path,
            media_type=media_type,
            runway_id=runway_id,
            original_filename=file.filename or saved_path.name,
            drone_id=drone_id,
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
                "runway_id": runway_id,
                "global_state": payload.global_state,
                "confidence": payload.confidence,
                "processing_ms": payload.processing_ms,
                "log_id": log.id,
            },
        )
        return payload
    except RuntimeError as exc:
        # Log the real error server-side; return a generic message so internal paths
        # or library internals are not disclosed to the client (rubric LR1D).
        logger.exception("analysis.runtime_error", extra={"runway_id": runway_id})
        raise HTTPException(
            status_code=503,
            detail="Inference service is temporarily unavailable. Check the server logs.",
        ) from exc
    except ValueError as exc:
        logger.warning("analysis.value_error", extra={"runway_id": runway_id, "detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        saved_path.unlink(missing_ok=True)


@router.get("/runways", response_model=list[RunwayResponse])
def get_runways() -> list[RunwayResponse]:
    return list_runways()


@router.get("/model", response_model=ModelInfo)
def get_model_info(_auth: Annotated[None, Depends(require_api_key)] = None) -> ModelInfo:
    return get_inference_service().model_info()


@router.get("/system", response_model=SystemInfo)
def get_system(_auth: Annotated[None, Depends(require_api_key)] = None) -> SystemInfo:
    """Host + runtime facts (audit IMP-BE-7) — every value read from the running host."""
    import platform as platform_module
    from importlib.metadata import PackageNotFoundError, version

    settings = get_settings()
    torch_available = cuda_available = False
    cuda_device_count = 0
    try:
        import torch

        torch_available = True
        cuda_available = bool(torch.cuda.is_available())
        cuda_device_count = torch.cuda.device_count() if cuda_available else 0
    except Exception:  # noqa: BLE001 - the torch probe is best-effort
        pass

    try:
        app_version = version("papi-detection")
    except PackageNotFoundError:
        app_version = "unknown"

    return SystemInfo(
        platform=platform_module.platform(),
        python_version=platform_module.python_version(),
        cpu_count=os.cpu_count(),
        torch_available=torch_available,
        cuda_available=cuda_available,
        cuda_device_count=cuda_device_count,
        device_configured=settings.device,
        app_version=app_version,
    )


@router.get("/stats", response_model=InferenceStats)
def get_stats(
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> InferenceStats:
    # Aggregates the whole analysis_logs table now (audit IMP-BE-2), so no limit param.
    return AnalysisLogRepository(db).stats()


def _log_filters(
    runway_id: str | None,
    media_type: str | None,
    global_state: str | None,
    created_after: str | None,
    min_confidence: float | None,
) -> dict:
    """Validate + normalise the shared log query filters (audit IMP-BE-3)."""
    parsed_after = None
    if created_after:
        try:
            parsed_after = datetime.fromisoformat(created_after)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="created_after must be ISO 8601, e.g. 2026-05-01 or 2026-05-01T12:00:00.",
            ) from exc
    return {
        "runway_id": runway_id,
        "media_type": media_type,
        "global_state": global_state,
        "created_after": parsed_after,
        "min_confidence": min_confidence,
    }


_CSV_COLUMNS = [
    "id", "created_at", "media_type", "runway_id", "global_state", "confidence",
    "angle_available", "elevation_angle_deg", "frame_count", "processing_ms",
    "original_filename",
]


@router.get("/logs", response_model=list[LogListItem])
def list_logs(
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    runway_id: str | None = None,
    media_type: str | None = None,
    global_state: str | None = None,
    created_after: str | None = None,
    min_confidence: float | None = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> list[LogListItem]:
    """Recent analysis logs, newest first.

    Optional filters plus an ``X-Total-Count`` header so the History page can paginate
    ("page N of M") instead of fetching everything and slicing client-side (audit IMP-BE-3).
    """
    filters = _log_filters(runway_id, media_type, global_state, created_after, min_confidence)
    repository = AnalysisLogRepository(db)
    response.headers["X-Total-Count"] = str(repository.count(**filters))
    return [repository.to_list_item(log) for log in repository.list_recent(limit, offset, **filters)]


@router.get("/logs/export.csv")
def export_logs_csv(
    runway_id: str | None = None,
    media_type: str | None = None,
    global_state: str | None = None,
    created_after: str | None = None,
    min_confidence: float | None = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> StreamingResponse:
    """Download the (optionally filtered) analysis log as CSV (audit IMP-BE-6).

    Declared before ``/logs/{log_id}`` so the literal path is not captured as an id.
    """
    filters = _log_filters(runway_id, media_type, global_state, created_after, min_confidence)
    rows = AnalysisLogRepository(db).iter_filtered(**filters)

    def generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_CSV_COLUMNS)
        for log in rows:
            created = log.created_at.isoformat() if hasattr(log.created_at, "isoformat") else log.created_at
            writer.writerow([
                log.id, created, log.media_type, log.runway_id, log.global_state,
                log.confidence, log.angle_available, log.elevation_angle_deg,
                log.frame_count, log.processing_ms, log.original_filename,
            ])
        yield buffer.getvalue()

    headers = {"Content-Disposition": "attachment; filename=papi_analysis_logs.csv"}
    return StreamingResponse(generate(), media_type="text/csv", headers=headers)


@router.get("/logs/{log_id}", response_model=AnalysisPayload)
def get_log(
    log_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> AnalysisPayload:
    log = AnalysisLogRepository(db).get(log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Analysis log not found.")
    payload = AnalysisPayload(**log.result_json)
    payload.log_id = log.id
    return payload
