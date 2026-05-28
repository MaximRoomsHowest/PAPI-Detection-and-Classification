import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.services.inference import get_inference_service
from app.services.media import detect_media_type, save_upload
from app.services.runways import get_runway, list_runways
from app.validation.analyze import parse_manual_drone_metadata
from app.validation.schemas import AnalysisPayload, FrameBatchPayload, LogListItem, RunwayResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def require_api_key(x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None) -> None:
    settings = get_settings()
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


@router.post("/analyze", response_model=AnalysisPayload)
async def analyze_media(
    file: Annotated[UploadFile, File()],
    # Default to papi_24 (confirmed lamp altitude 467.609 m) rather than
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
    # Default to papi_24 (confirmed lamp altitude 467.609 m) rather than
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
    # Default to papi_24 (confirmed lamp altitude 467.609 m) rather than
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
        logger.exception("analysis.runtime_error", extra={"runway_id": runway_id})
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("analysis.value_error", extra={"runway_id": runway_id, "detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        saved_path.unlink(missing_ok=True)


@router.get("/runways", response_model=list[RunwayResponse])
def get_runways() -> list[RunwayResponse]:
    return list_runways()


@router.get("/logs", response_model=list[LogListItem])
def list_logs(
    limit: int = 50,
    offset: int = 0,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(require_api_key)] = None,
) -> list[LogListItem]:
    repository = AnalysisLogRepository(db)
    return [repository.to_list_item(log) for log in repository.list_recent(limit, offset)]


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
