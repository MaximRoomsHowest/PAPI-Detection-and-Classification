from datetime import datetime
from math import isfinite

from sqlalchemy import ColumnElement, desc, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AnalysisLog
from app.services.media import media_url_for_path
from app.services.storage import get_media_storage
from app.validation.schemas import AnalysisPayload, InferenceStats, LogListItem

_GLOBAL_STATES = {
    "far_too_high",
    "too_high",
    "correct_glidepath",
    "too_low",
    "far_too_low",
    "transition",
    "unknown",
}


class AnalysisLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_from_payload(self, payload: AnalysisPayload) -> AnalysisLog:
        settings = get_settings()
        lamp_state = {lamp.index: lamp.state for lamp in payload.lamps}
        artifact_path = _artifact_reference_from_url(payload.artifact_url, settings)

        log = AnalysisLog(
            media_type=payload.media_type,
            # Width-cap like its siblings below: add_runway now caps derived ids,
            # but a pre-cap stored custom runway (or a future id source) must not
            # 503 the log commit on Postgres (StringDataRightTruncation).
            runway_id=payload.runway_id[:96],
            # Cap at the column width (VARCHAR(128)), like original_filename below: an
            # unbounded client-supplied drone_id otherwise raises StringDataRightTruncation
            # (503) on Postgres and orphans the just-written artifact (SQLite tests don't
            # enforce width) — audit.
            drone_id=(payload.drone_id[:128] if payload.drone_id else None),
            # Registry model ids are short ("small"/"nano"); the width cap mirrors
            # drone_id above so an unexpected value can't 503 on Postgres (audit COL-1).
            model_id=(payload.model_id[:96] if payload.model_id else None),
            # Cap at the column width (VARCHAR(512)): a pathologically long upload name
            # otherwise raises a StringDataRightTruncation 503 on Postgres while orphaning
            # the just-written artifact (SQLite tests don't enforce width) — audit.
            original_filename=(payload.original_filename or "")[:512],
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
        try:
            self.db.commit()
        except Exception:
            # The annotated artifact was written by inference BEFORE this commit. If the
            # row never persists (DB error, a column-width truncation, etc.) the artifact
            # would orphan on disk with no log pointing to it. Roll the transaction back
            # and delete the file so a failed persist leaves nothing behind (audit P3).
            # ``artifact_path`` is already the resolved, in-exports-tree path (or None).
            self.db.rollback()
            if artifact_path:
                get_media_storage(settings).delete_reference(artifact_path)
            raise
        self.db.refresh(log)
        return log

    @staticmethod
    def _filter_conditions(
        runway_id: str | None = None,
        media_type: str | None = None,
        global_state: str | None = None,
        created_after: datetime | None = None,
        min_confidence: float | None = None,
        model_id: str | None = None,
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
        if model_id:
            # Column-only match: rows from before the model_id column stay NULL
            # (no backfill — see app/migrations.py) and are not matched here.
            conditions.append(AnalysisLog.model_id == model_id)
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

    def stats(self, **filters) -> InferenceStats:
        """Aggregate over the (optionally filtered) analysis-log table.

        Accepts the same filter set as list/count/export, so the History page's
        summary cards can describe the filtered slice the table is showing
        instead of always the whole table (audit IMP-BE-2 + History deep dive).
        Counts / averages / breakdowns use SQL aggregates over the indexed columns.
        Latency percentiles are computed in Python over the processing_ms column —
        portable across SQLite (tests) and Postgres (prod), and cheap at this scale.
        """
        conditions = self._filter_conditions(**filters)
        total = int(
            self.db.scalar(select(func.count()).select_from(AnalysisLog).where(*conditions)) or 0
        )
        if total == 0:
            return InferenceStats(sample_size=0, total_analyses=0, image_count=0, video_count=0)

        by_media = _grouped_counts(self.db, AnalysisLog.media_type, conditions)
        by_runway = _grouped_counts(self.db, AnalysisLog.runway_id, conditions)
        by_state = _grouped_counts(self.db, AnalysisLog.global_state, conditions)
        avg_proc = self.db.scalar(select(func.avg(AnalysisLog.processing_ms)).where(*conditions))
        avg_conf = self.db.scalar(select(func.avg(AnalysisLog.confidence)).where(*conditions))
        first_at = self.db.scalar(select(func.min(AnalysisLog.created_at)).where(*conditions))
        latest_at = self.db.scalar(select(func.max(AnalysisLog.created_at)).where(*conditions))
        processing_times = sorted(
            self.db.scalars(select(AnalysisLog.processing_ms).where(*conditions)).all()
        )

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
        result = log.result_json if isinstance(log.result_json, dict) else {}
        global_state, confidence, frame_count = _video_display_summary(
            result,
            fallback_state=log.global_state,
            fallback_confidence=log.confidence,
            fallback_frame_count=log.frame_count,
        )
        return LogListItem(
            id=log.id,
            media_type=log.media_type,
            runway_id=log.runway_id,
            drone_id=log.drone_id,
            original_filename=log.original_filename,
            # Column first; result_json fallback covers rows written before the
            # model_id column existed (audit COL-1).
            model_id=log.model_id or result.get("model_id"),
            model_label=result.get("model_label"),
            model_role=result.get("model_role"),
            global_state=global_state,
            confidence=confidence,
            angle_available=log.angle_available,
            elevation_angle_deg=log.elevation_angle_deg,
            frame_count=frame_count,
            processing_ms=log.processing_ms,
            # Partial-result flags live only in result_json (no dedicated columns);
            # without them the list/CSV showed a half-decoded or cap-truncated
            # analysis as indistinguishable from a complete one (audit 2026-06-12).
            truncated_at_frame=result.get("truncated_at_frame"),
            decode_shortfall=result.get("decode_shortfall"),
            artifact_url=media_url_for_path(log.artifact_path, get_settings()),
            created_at=log.created_at.isoformat(),
        )


def _artifact_reference_from_url(artifact_url: str | None, settings) -> str | None:
    """Resolve an artifact URL to the storage reference saved in the database.

    The happy path is a server-generated ``/media/<uuid>_annotated.<ext>`` (a bare
    filename, see ``InferenceService``), which joins cleanly under ``exports_dir`` in
    local mode or maps to ``exports/<filename>`` in Azure Blob mode.
    This is a defence-in-depth guard: if a crafted ``artifact_url`` ever smuggled in
    ``..`` segments and escaped the exports tree, we store None rather than persist an
    out-of-tree/blob path. ``media_url_for_path`` already drops such paths on read-back;
    this keeps them out of the column on write too.
    """
    if not artifact_url:
        return None
    relative = artifact_url.removeprefix("/media/").replace("\\", "/").lstrip("/")
    if not relative or relative.startswith("../") or "/../" in f"/{relative}/":
        return None
    if getattr(settings, "storage_backend", "local") == "azure_blob":
        return f"exports/{relative}"
    candidate = settings.exports_dir / relative
    try:
        candidate.resolve().relative_to(settings.exports_dir.resolve())
    except ValueError:
        return None
    return str(candidate)


def _video_display_summary(
    result: dict,
    *,
    fallback_state: str,
    fallback_confidence: float,
    fallback_frame_count: int,
) -> tuple[str, float, int]:
    """Derive list-row video headline fields from every persisted frame.

    Legacy video rows can have column-level state/confidence copied from one
    representative frame. The full result_json still carries per_frame, so use it
    for display without fetching every detail payload.
    """

    if result.get("media_type") != "video":
        return fallback_state, fallback_confidence, fallback_frame_count
    raw_samples = result.get("per_frame")
    if not isinstance(raw_samples, list):
        return fallback_state, fallback_confidence, fallback_frame_count

    samples = [sample for sample in raw_samples if isinstance(sample, dict)]
    if not samples:
        return fallback_state, fallback_confidence, fallback_frame_count

    state_counts: dict[str, int] = {}
    confidences: list[float] = []
    for sample in samples:
        state = sample.get("state")
        if state in _GLOBAL_STATES:
            state_counts[state] = state_counts.get(state, 0) + 1
        confidence = sample.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            value = float(confidence)
            if isfinite(value):
                confidences.append(value)

    state = (
        max(state_counts.items(), key=lambda item: item[1])[0]
        if state_counts
        else fallback_state
    )
    confidence = sum(confidences) / len(confidences) if confidences else fallback_confidence
    return state, confidence, len(samples)


def _percentile_nearest_rank(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    index = max(0, min(len(values) - 1, round((len(values) - 1) * percentile)))
    return values[index]


def _grouped_counts(
    db: Session, column: ColumnElement, conditions: list[ColumnElement[bool]] | None = None
) -> dict[str, int]:
    stmt = select(column, func.count()).where(*(conditions or [])).group_by(column)
    rows = db.execute(stmt).all()
    return {str(key): int(value) for key, value in rows}


def _iso(value: datetime | str | None) -> str | None:
    """created_at comes back as a datetime (Postgres) or an ISO string (SQLite).

    The isinstance check narrows the str case, leaving datetime for .isoformat()
    so no `type: ignore` is needed.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()
