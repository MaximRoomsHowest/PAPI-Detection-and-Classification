"""Persisted-analysis endpoints: list, CSV export, and detail.

Route order matters: ``/logs/export.csv`` is declared before ``/logs/{log_id}``
so the literal ``export.csv`` segment is not captured as a ``log_id`` path
param. FastAPI matches routes in declaration order, so keep that ordering.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.api._csv import stream_log_rows
from app.api._filters import parse_log_filters
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.validation.schemas import AnalysisPayload, LogListItem

router = APIRouter(prefix="/api")


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
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> list[LogListItem]:
    """Recent analysis logs, newest first.

    Optional filters plus an ``X-Total-Count`` header so the History page can paginate
    ("page N of M") instead of fetching everything and slicing client-side (audit IMP-BE-3).
    """
    filters = parse_log_filters(runway_id, media_type, global_state, created_after, min_confidence)
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
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> StreamingResponse:
    """Download the (optionally filtered) analysis log as CSV (audit IMP-BE-6).

    Declared before ``/logs/{log_id}`` so the literal path is not captured as an id.
    """
    filters = parse_log_filters(runway_id, media_type, global_state, created_after, min_confidence)
    rows = AnalysisLogRepository(db).iter_filtered(**filters)

    headers = {"Content-Disposition": "attachment; filename=papi_analysis_logs.csv"}
    return StreamingResponse(stream_log_rows(rows), media_type="text/csv", headers=headers)


@router.get("/logs/{log_id}", response_model=AnalysisPayload)
def get_log(
    log_id: str,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> AnalysisPayload:
    log = AnalysisLogRepository(db).get(log_id)
    if log is None:
        raise HTTPException(status_code=404, detail="Analysis log not found.")
    payload = AnalysisPayload(**log.result_json)
    payload.log_id = log.id
    return payload
