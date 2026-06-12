"""Shared query-filter parsing for the log list + CSV export routes.

``/api/logs`` and ``/api/logs/export.csv`` accept the same optional filter
set; keeping the parse/normalise step in one place (audit IMP-BE-3) means the
two routes can never drift on, e.g., how ``created_after`` is validated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import get_args

from fastapi import HTTPException

from app.validation.schemas import GlobalState, MediaType

_MEDIA_TYPES = set(get_args(MediaType))
_GLOBAL_STATES = set(get_args(GlobalState))
_MAX_TEXT_FILTER_LENGTH = 120


def _clean_optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > _MAX_TEXT_FILTER_LENGTH:
        raise HTTPException(status_code=400, detail=f"{field_name} is too long.")
    return cleaned


def parse_log_filters(
    runway_id: str | None,
    media_type: str | None,
    global_state: str | None,
    created_after: str | None,
    min_confidence: float | None,
    model_id: str | None = None,
) -> dict:
    """Validate + normalise the shared log query filters (audit IMP-BE-3).

    Values are validated before they hit the repository so the list and CSV
    endpoints reject the same malformed filters instead of silently returning
    empty result sets for impossible states or out-of-range confidence values.

    ``model_id`` is intentionally NOT validated against the live registry:
    logs may reference a model that has since been removed from models.json.
    """
    runway_id = _clean_optional_text(runway_id, "runway_id")
    media_type = _clean_optional_text(media_type, "media_type")
    global_state = _clean_optional_text(global_state, "global_state")
    created_after = _clean_optional_text(created_after, "created_after")
    model_id = _clean_optional_text(model_id, "model_id")

    if media_type is not None and media_type not in _MEDIA_TYPES:
        raise HTTPException(status_code=400, detail="media_type must be one of: image, video.")

    if global_state is not None and global_state not in _GLOBAL_STATES:
        allowed = ", ".join(sorted(_GLOBAL_STATES))
        raise HTTPException(status_code=400, detail=f"global_state must be one of: {allowed}.")

    if min_confidence is not None and (
        not isfinite(min_confidence) or not 0.0 <= min_confidence <= 1.0
    ):
        raise HTTPException(status_code=400, detail="min_confidence must be between 0 and 1.")

    parsed_after = None
    if created_after:
        iso_value = created_after[:-1] + "+00:00" if created_after.endswith("Z") else created_after
        try:
            parsed_after = datetime.fromisoformat(iso_value)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="created_after must be ISO 8601, e.g. 2026-05-01 or 2026-05-01T12:00:00.",
            ) from exc
        if parsed_after.tzinfo is None:
            # A date-only or naive timestamp is read as UTC, matching the stored-UTC
            # convention; otherwise Postgres compares it in the server's session TimeZone
            # and silently shifts the filter boundary vs SQLite (audit).
            parsed_after = parsed_after.replace(tzinfo=timezone.utc)
    return {
        "runway_id": runway_id,
        "media_type": media_type,
        "global_state": global_state,
        "created_after": parsed_after,
        "min_confidence": min_confidence,
        "model_id": model_id,
    }
