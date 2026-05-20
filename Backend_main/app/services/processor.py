from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.models import AnalysisJob, AnalysisResult
from app.services.inference import InferenceService


def process_analysis_job(job_id: str) -> None:
    settings = get_settings()
    service = InferenceService(settings)

    with SessionLocal() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = "running"
        job.progress = 5
        job.started_at = datetime.utcnow()
        db.commit()

    try:
        with SessionLocal() as db:
            job = db.get(AnalysisJob, job_id)
            if job is None:
                return
            media_path = Path(job.temp_input_path)
            media_type = job.media_type
            runway_id = job.runway_id

        payload = service.analyze(media_path, media_type, runway_id)

        with SessionLocal() as db:
            job = db.get(AnalysisJob, job_id)
            if job is None:
                return
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.utcnow()
            if payload.artifact_url:
                artifact_name = payload.artifact_url.removeprefix("/media/")
                job.artifact_path = str(settings.exports_dir / artifact_name)

            lamp_state = {lamp.index: lamp.state for lamp in payload.lamps}
            db.add(
                AnalysisResult(
                    job_id=job.id,
                    global_state=payload.global_state,
                    lamp_1_state=lamp_state.get(1, "unknown"),
                    lamp_2_state=lamp_state.get(2, "unknown"),
                    lamp_3_state=lamp_state.get(3, "unknown"),
                    lamp_4_state=lamp_state.get(4, "unknown"),
                    confidence=payload.confidence,
                    angle_available=payload.angle.angle_available,
                    elevation_angle_deg=payload.angle.elevation_angle_deg,
                    frame_count=payload.frame_count,
                    processing_ms=payload.processing_ms,
                    model_name="YOLO",
                    model_version=settings.model_path.name,
                    result_json=payload.model_dump(),
                )
            )
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(AnalysisJob, job_id)
            if job is None:
                return
            job.status = "failed"
            job.progress = 100
            job.completed_at = datetime.utcnow()
            job.error_message = str(exc)
            db.commit()

