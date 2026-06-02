"""Shared query-filter parsing for the log list + CSV export routes.

``/api/logs`` and ``/api/logs/export.csv`` accept the same optional filter
set; keeping the parse/normalise step in one place (audit IMP-BE-3) means the
two routes can never drift on, e.g., how ``created_after`` is validated.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException


def parse_log_filters(
    runway_id: str | None,
    media_type: str | None,
    global_state: str | None,
    created_after: str | None,
    min_confidence: float | None,
) -> dict:
    """Validate + normalise the shared log query filters (audit IMP-BE-3).

    ``created_after`` is the only field that needs parsing: it arrives as a
    free-text query string and must be ISO 8601. Everything else is passed
    through verbatim to the repository.
    """
    parsed_after = None
    if created_after:
        try:
            parsed_after = datetime.fromisoformat(created_after)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="created_after must be ISO 8601, e.g. 2026-05-01 or 2026-05-01T12:00:00.",
            ) from exc
    return {
        "runway_id": runway_id,
        "media_type": media_type,
        "global_state": global_state,
        "created_after": parsed_after,
        "min_confidence": min_confidence,
    }
