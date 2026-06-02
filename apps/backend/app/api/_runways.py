"""Request-time runway_id validation shared by the analyze endpoints.

``get_runway`` already raises ``ValueError`` for an unknown id; the analyze
routes need that as an HTTP 400 *before* any upload is written to disk, so an
invalid request can't leak a saved file. Centralising the translation here
keeps /analyze, /analyze-frame(s) and /analyze-sequence identical.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.services.runways import get_runway


def validate_runway_id(runway_id: str) -> None:
    """Raise HTTP 400 if ``runway_id`` is not a known runway.

    Rejects an unknown runway before disk I/O (verified fix): an attacker (or a
    typo'd frontend) can no longer cause an upload to be saved for a runway that
    doesn't exist.
    """
    try:
        get_runway(runway_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
