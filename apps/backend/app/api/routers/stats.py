"""Aggregate statistics over the whole analysis-log table."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import app.api.routes as routes
from app.database import get_session
from app.repositories import AnalysisLogRepository
from app.validation.schemas import InferenceStats

router = APIRouter(prefix="/api")


@router.get("/stats", response_model=InferenceStats)
def get_stats(
    db: Annotated[Session, Depends(get_session)] = None,
    _auth: Annotated[None, Depends(routes.require_api_key)] = None,
) -> InferenceStats:
    # Aggregates the whole analysis_logs table now (audit IMP-BE-2), so no limit param.
    return AnalysisLogRepository(db).stats()
