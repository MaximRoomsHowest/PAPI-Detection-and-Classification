"""Aggregate statistics over the (optionally filtered) analysis-log table."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.api._filters import parse_log_filters
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.validation.schemas import InferenceStats

router = APIRouter(prefix="/api")


@router.get("/stats", response_model=InferenceStats)
def get_stats(
    runway_id: str | None = None,
    media_type: str | None = None,
    global_state: str | None = None,
    created_after: str | None = None,
    min_confidence: float | None = None,
    model_id: str | None = None,
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> InferenceStats:
    """Aggregates over all rows by default (audit IMP-BE-2, so no limit param);
    accepts the same optional filters as ``/api/logs`` so the History summary
    cards can describe exactly the slice the filtered table is showing.
    """
    filters = parse_log_filters(
        runway_id, media_type, global_state, created_after, min_confidence, model_id
    )
    return AnalysisLogRepository(db).stats(**filters)
