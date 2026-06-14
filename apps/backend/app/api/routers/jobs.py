"""Background-job status + cancellation endpoints (api-key gated).

The frontend polls ``GET /api/jobs/{id}`` while a job is queued/running. Both job
kinds (evaluate / label_assist) report through the same shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.database import get_session
from app.models.job import Job
from app.repositories.jobs import JobRepository
from app.validation.schemas import JobResponse

router = APIRouter(prefix="/api")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else value.isoformat()


def job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        kind=job.kind,
        status=job.status,
        phase=job.phase,
        progress=job.progress,
        params=dict(job.params_json or {}),
        result=job.result_json,
        error=job.error,
        created_at=_iso(job.created_at),
        started_at=_iso(job.started_at),
        finished_at=_iso(job.finished_at),
    )


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    kind: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> list[JobResponse]:
    jobs = JobRepository(db).list(kind=kind, status=status, limit=limit, offset=offset)
    return [job_to_response(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(
    job_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> JobResponse:
    job = JobRepository(db).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job.")
    return job_to_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(
    job_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> JobResponse:
    job = JobRepository(db).request_cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job.")
    return job_to_response(job)
