from datetime import datetime

from sqlalchemy import ColumnElement, desc, func, select
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

    @staticmethod
    def _filter_conditions(
        runway_id: str | None = None,
        media_type: str | None = None,
        global_state: str | None = None,
        created_after: datetime | None = None,
        min_confidence: float | None = None,
    ) -> list[ColumnElement[bool]]:
        """WHERE clauses shared by list / count / export (audit IMP-BE-3)."""
        conditions: list[ColumnElement[bool]] = []
        if runway_id:
            conditions.append(AnalysisLog.runway_id == runway_id)
        if media_type:
            conditions.append(AnalysisLog.media_type == media_type)
        if global_state:
            conditions.append(AnalysisLog.global_state == global_state)
        if created_after is not None:
            conditions.append(AnalysisLog.created_at >= created_after)
        if min_confidence is not None:
            conditions.append(AnalysisLog.confidence >= min_confidence)
        return conditions

    def list_recent(self, limit: int, offset: int, **filters) -> list[AnalysisLog]:
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        stmt = (
            select(AnalysisLog)
            .where(*self._filter_conditions(**filters))
            .order_by(desc(AnalysisLog.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def count(self, **filters) -> int:
        stmt = select(func.count()).select_from(AnalysisLog).where(*self._filter_conditions(**filters))
        return int(self.db.scalar(stmt) or 0)

    def iter_filtered(self, **filters) -> list[AnalysisLog]:
        """All matching rows, newest first, for CSV export (audit IMP-BE-6)."""
        stmt = (
            select(AnalysisLog)
            .where(*self._filter_conditions(**filters))
            .order_by(desc(AnalysisLog.created_at))
        )
        return list(self.db.scalars(stmt).all())

    def get(self, log_id: str) -> AnalysisLog | None:
        return self.db.get(AnalysisLog, log_id)

    def stats(self) -> InferenceStats:
        """Whole-table aggregate (audit IMP-BE-2).

        Counts / averages / breakdowns use SQL aggregates over the indexed columns.
        Latency percentiles are computed in Python over the processing_ms column —
        portable across SQLite (tests) and Postgres (prod), and cheap at this scale.
        """
        total = int(self.db.scalar(select(func.count()).select_from(AnalysisLog)) or 0)
        if total == 0:
            return InferenceStats(sample_size=0, total_analyses=0, image_count=0, video_count=0)

        by_media = _grouped_counts(self.db, AnalysisLog.media_type)
        by_runway = _grouped_counts(self.db, AnalysisLog.runway_id)
        by_state = _grouped_counts(self.db, AnalysisLog.global_state)
        avg_proc = self.db.scalar(select(func.avg(AnalysisLog.processing_ms)))
        avg_conf = self.db.scalar(select(func.avg(AnalysisLog.confidence)))
        first_at = self.db.scalar(select(func.min(AnalysisLog.created_at)))
        latest_at = self.db.scalar(select(func.max(AnalysisLog.created_at)))
        processing_times = sorted(self.db.scalars(select(AnalysisLog.processing_ms)).all())

        return InferenceStats(
            sample_size=total,
            total_analyses=total,
            image_count=by_media.get("image", 0),
            video_count=by_media.get("video", 0),
            avg_processing_ms=round(float(avg_proc), 2) if avg_proc is not None else None,
            p50_processing_ms=_percentile_nearest_rank(processing_times, 0.50),
            p95_processing_ms=_percentile_nearest_rank(processing_times, 0.95),
            avg_confidence=round(float(avg_conf), 4) if avg_conf is not None else None,
            by_runway=by_runway,
            by_global_state=by_state,
            by_media_type=by_media,
            first_analysis_at=_iso(first_at),
            latest_created_at=_iso(latest_at),
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


def _grouped_counts(db: Session, column: ColumnElement) -> dict[str, int]:
    rows = db.execute(select(column, func.count()).group_by(column)).all()
    return {str(key): int(value) for key, value in rows}


def _iso(value: object) -> str | None:
    """created_at may come back as a datetime (Postgres) or an ISO string (SQLite)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()  # type: ignore[attr-defined]

