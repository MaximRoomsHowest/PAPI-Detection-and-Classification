"""Persistence for background jobs (``jobs`` table).

Thin CRUD around the durable job state the one-worker runner and the polling
endpoints share. The runner opens its OWN session and uses this repo from the
worker thread; request handlers use it from the request session.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session

from app.models.analysis_log import utcnow_aware
from app.models.job import Job

# Terminal statuses a job can never leave.
TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")


class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, kind: str, params: dict[str, Any]) -> Job:
        job = Job(kind=kind, status="queued", params_json=params, progress=0.0)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.db.get(Job, job_id)

    def list(
        self,
        kind: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        limit = min(max(limit, 1), 200)
        offset = max(offset, 0)
        conditions = []
        if kind:
            conditions.append(Job.kind == kind)
        if status:
            conditions.append(Job.status == status)
        stmt = (
            select(Job)
            .where(*conditions)
            .order_by(desc(Job.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt).all())

    def mark_running(self, job_id: str) -> int:
        """Compare-and-swap ``queued`` -> ``running``. Returns the number of rows
        updated: 0 means the job was cancelled (or otherwise left ``queued``) in the
        window after the worker's status check, so the caller must NOT run it. The
        ``WHERE status == 'queued'`` guard is what makes a concurrent cancel win."""
        result = self.db.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(status="running", phase="starting", started_at=utcnow_aware())
        )
        self.db.commit()
        return int(result.rowcount or 0)

    def set_progress(self, job_id: str, phase: str | None = None, progress: float | None = None) -> None:
        values: dict[str, Any] = {}
        if phase is not None:
            values["phase"] = phase[:64]
        if progress is not None:
            values["progress"] = max(0.0, min(1.0, float(progress)))
        if not values:
            return
        self.db.execute(update(Job).where(Job.id == job_id).values(**values))
        self.db.commit()

    def mark_succeeded(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        self.db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                status="succeeded",
                phase="done",
                progress=1.0,
                result_json=result,
                finished_at=utcnow_aware(),
            )
        )
        self.db.commit()

    def mark_failed(self, job_id: str, error: str) -> None:
        self.db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="failed", error=error[:4000], finished_at=utcnow_aware())
        )
        self.db.commit()

    def mark_cancelled(self, job_id: str) -> None:
        self.db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="cancelled", phase="cancelled", finished_at=utcnow_aware())
        )
        self.db.commit()

    def request_cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status in TERMINAL_STATUSES:
            return job
        job.cancel_requested = True
        # A still-queued job can be cancelled immediately; a running one is
        # cancelled cooperatively by its handler at the next checkpoint.
        if job.status == "queued":
            job.status = "cancelled"
            job.phase = "cancelled"
            job.finished_at = utcnow_aware()
        self.db.commit()
        self.db.refresh(job)
        return job

    def is_cancel_requested(self, job_id: str) -> bool:
        value = self.db.scalar(select(Job.cancel_requested).where(Job.id == job_id))
        return bool(value)

    def reconcile_orphans(self) -> int:
        """Mark jobs left ``running``/``queued`` by a dead process as failed."""
        result = self.db.execute(
            update(Job)
            .where(Job.status.in_(("running", "queued")))
            .values(
                status="failed",
                error="Interrupted by a backend restart (no resume).",
                finished_at=utcnow_aware(),
            )
        )
        self.db.commit()
        return int(result.rowcount or 0)
