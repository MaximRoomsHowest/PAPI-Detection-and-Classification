"""CSV serialisation for the analysis-log export (audit IMP-BE-6).

Isolated from the route handler so the column order, the formula-injection
guard, and the streaming generator live together and stay in sync.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator

# Column order for the export. Kept as a module constant so a future column
# add/remove is a one-line change and the header row + value row can never
# drift apart.
CSV_COLUMNS = [
    "id", "created_at", "media_type", "runway_id", "global_state", "confidence",
    "angle_available", "elevation_angle_deg", "frame_count", "processing_ms",
    "original_filename",
]


def csv_safe(value) -> str:
    """Neutralise CSV/formula injection (CWE-1236).

    A cell starting with ``= + - @`` or a control char can execute when the
    export is opened in a spreadsheet, so force such a cell to a literal with a
    leading apostrophe (audit M3). Only the FIRST character matters — that is
    the OWASP-correct trigger, so the check stays anchored to ``text[:1]``.

    Applied to every attacker-controlled free-text column: ``original_filename``
    (arbitrary upload name) and ``runway_id`` (now validated against the known
    set, but escaped defensively in case validation is ever relaxed).
    """
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def stream_log_rows(rows: Iterable) -> Iterator[str]:
    """Yield the CSV body for ``rows`` (header + one line per log).

    ``rows`` is the repository's fully-materialised filtered list, so iterating
    here touches no detached ORM state.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(CSV_COLUMNS)
    for log in rows:
        created = log.created_at.isoformat() if hasattr(log.created_at, "isoformat") else log.created_at
        writer.writerow([
            log.id, created, log.media_type, csv_safe(log.runway_id), log.global_state,
            log.confidence, log.angle_available, log.elevation_angle_deg,
            log.frame_count, log.processing_ms, csv_safe(log.original_filename),
        ])
    yield buffer.getvalue()
