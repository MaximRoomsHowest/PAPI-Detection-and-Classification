from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_session
from app.models import AnalysisJob
from app.schemas import AnalyzeAccepted, AnalysisJobResponse, AnalysisPayload, LogListItem, RunwayResponse
from app.services.media import detect_media_type, media_url_for_path, save_upload
from app.services.processor import process_analysis_job
from app.services.runways import get_runway, list_runways


router = APIRouter(prefix="/api")


@router.post("/analyze", response_model=AnalyzeAccepted, status_code=202)
async def analyze_media(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    runway_id: str = Form("papi_06"),
    drone_id: str | None = Form(None),
    notes: str | None = Form(None),
    db: Session = Depends(get_session),
) -> AnalyzeAccepted:
    settings = get_settings()
    try:
        get_runway(runway_id)
        media_type = detect_media_type(file.filename or "", file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    saved_path = await save_upload(file, settings)
    job = AnalysisJob(
        status="pending",
        progress=0,
        media_type=media_type,
        runway_id=runway_id,
        drone_id=drone_id,
        notes=notes,
        original_filename=file.filename or Path(saved_path).name,
        temp_input_path=str(saved_path),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_analysis_job, job.id)
    return AnalyzeAccepted(job_id=job.id, status=job.status)


@router.get("/analyze/{job_id}", response_model=AnalysisJobResponse)
def get_analysis_job(job_id: str, db: Session = Depends(get_session)) -> AnalysisJobResponse:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return _job_to_response(job)


@router.get("/logs", response_model=list[LogListItem])
def list_logs(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_session),
) -> list[LogListItem]:
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    jobs = db.scalars(
        select(AnalysisJob).order_by(desc(AnalysisJob.created_at)).limit(limit).offset(offset)
    ).all()
    return [
        LogListItem(
            id=job.id,
            status=job.status,
            media_type=job.media_type,
            runway_id=job.runway_id,
            drone_id=job.drone_id,
            original_filename=job.original_filename,
            global_state=job.result.global_state if job.result else None,
            confidence=job.result.confidence if job.result else None,
            elevation_angle_deg=job.result.elevation_angle_deg if job.result else None,
            created_at=job.created_at,
            completed_at=job.completed_at,
        )
        for job in jobs
    ]


@router.get("/logs/{job_id}", response_model=AnalysisJobResponse)
def get_log(job_id: str, db: Session = Depends(get_session)) -> AnalysisJobResponse:
    return get_analysis_job(job_id, db)


@router.get("/runways", response_model=list[RunwayResponse])
def get_runways() -> list[RunwayResponse]:
    return list_runways()


def _job_to_response(job: AnalysisJob) -> AnalysisJobResponse:
    settings = get_settings()
    payload = None
    if job.result:
        result_data = dict(job.result.result_json)
        result_data["artifact_url"] = result_data.get("artifact_url") or media_url_for_path(
            job.artifact_path,
            settings,
        )
        payload = AnalysisPayload(**result_data)

    return AnalysisJobResponse(
        id=job.id,
        status=job.status,
        progress=job.progress,
        media_type=job.media_type,
        runway_id=job.runway_id,
        drone_id=job.drone_id,
        notes=job.notes,
        original_filename=job.original_filename,
        artifact_url=media_url_for_path(job.artifact_path, settings),
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        result=payload,
    )

