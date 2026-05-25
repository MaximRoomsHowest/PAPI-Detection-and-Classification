from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.services.inference import get_inference_service
from app.services.media import detect_media_type, save_upload
from app.services.runways import get_runway, list_runways
from app.validation.analyze import parse_manual_drone_metadata
from app.validation.schemas import AnalysisPayload, LogListItem, RunwayResponse


router = APIRouter(prefix="/api")


@router.post("/analyze", response_model=AnalysisPayload)
async def analyze_media(
    file: UploadFile = File(...),
    runway_id: str = Form("papi_06"),
    drone_id: str | None = Form(None),
    drone_latitude: float | None = Form(None),
    drone_longitude: float | None = Form(None),
    drone_altitude_m: float | None = Form(None),
    db: Session = Depends(get_session),
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
    file: UploadFile = File(...),
    runway_id: str = Form("papi_06"),
    drone_id: str | None = Form(None),
    drone_latitude: float | None = Form(None),
    drone_longitude: float | None = Form(None),
    drone_altitude_m: float | None = Form(None),
    db: Session = Depends(get_session),
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
        return payload
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
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
    db: Session = Depends(get_session),
) -> list[LogListItem]:
    repository = AnalysisLogRepository(db)
    return [repository.to_list_item(log) for log in repository.list_recent(limit, offset)]


@router.get("/logs/{log_id}", response_model=AnalysisPayload)
def get_log(log_id: str, db: Session = Depends(get_session)) -> AnalysisPayload:
    log = AnalysisLogRepository(db).get(log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Analysis log not found.")
    payload = AnalysisPayload(**log.result_json)
    payload.log_id = log.id
    return payload
