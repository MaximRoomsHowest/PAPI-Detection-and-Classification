from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnalysisLog
from app.services.media import media_url_for_path
from app.validation.schemas import AnalysisPayload, InferenceStats, LogListItem


class AnalysisLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_from_payload(self, payload: AnalysisPayload) -> AnalysisLog:
        lamp_state = {lamp.index: lamp.state for lamp in payload.lamps}
        artifact_path = None
        if payload.artifact_url:
            artifact_path = str(get_settings().exports_dir / payload.artifact_url.removeprefix("/media/"))

        log = AnalysisLog(
            media_type=payload.media_type,
            runway_id=payload.runway_id,
            drone_id=payload.drone_id,
            original_filename=payload.original_filename,
            artifact_path=artifact_path,
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
            result_json=payload.model_dump(),
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log

    def list_recent(self, limit: int, offset: int) -> list[AnalysisLog]:
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        return list(
            self.db.scalars(
                select(AnalysisLog).order_by(desc(AnalysisLog.created_at)).limit(limit).offset(offset)
            ).all()
        )

    def get(self, log_id: str) -> AnalysisLog | None:
        return self.db.get(AnalysisLog, log_id)

    def stats(self, limit: int = 100) -> InferenceStats:
        logs = self.list_recent(limit=limit, offset=0)
        processing_times = sorted(log.processing_ms for log in logs)
        image_count = sum(1 for log in logs if log.media_type == "image")
        video_count = sum(1 for log in logs if log.media_type == "video")
        return InferenceStats(
            sample_size=len(logs),
            image_count=image_count,
            video_count=video_count,
            avg_processing_ms=round(sum(processing_times) / len(processing_times), 2)
            if processing_times
            else None,
            p50_processing_ms=_percentile_nearest_rank(processing_times, 0.50),
            p95_processing_ms=_percentile_nearest_rank(processing_times, 0.95),
            latest_created_at=logs[0].created_at.isoformat() if logs else None,
        )

    def to_list_item(self, log: AnalysisLog) -> LogListItem:
        return LogListItem(
            id=log.id,
            media_type=log.media_type,
            runway_id=log.runway_id,
            drone_id=log.drone_id,
            original_filename=log.original_filename,
            global_state=log.global_state,
            confidence=log.confidence,
            angle_available=log.angle_available,
            elevation_angle_deg=log.elevation_angle_deg,
            frame_count=log.frame_count,
            processing_ms=log.processing_ms,
            artifact_url=media_url_for_path(log.artifact_path, get_settings()),
            created_at=log.created_at.isoformat(),
        )


def _percentile_nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, round((len(values) - 1) * percentile)))
    return values[index]

