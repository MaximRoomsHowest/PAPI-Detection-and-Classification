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
    "id", "created_at", "media_type", "runway_id", "drone_id", "global_state", "confidence",
    "angle_available", "elevation_angle_deg", "frame_count", "truncated_at_frame",
    "decode_shortfall", "processing_ms",
    "model_id", "model_label", "model_role", "original_filename",
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
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r", "\n") else text


def stream_log_rows(rows: Iterable) -> Iterator[str]:
    """Yield the CSV export incrementally — the header, then one chunk per log row.

    Each row is written into a small reused buffer that is truncated after every yield,
    so this serializer holds only one row of CSV text at a time instead of building the
    whole body in memory, and the StreamingResponse flushes each chunk as it is produced.
    Note: ``rows`` is already materialized by the caller (``iter_filtered`` does
    ``list(...)``), so end-to-end peak memory is still bounded by the matching row set —
    this generator removes the second, serialized-CSV copy, not the ORM-row copy.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    def _drain() -> str:
        chunk = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return chunk

    writer.writerow(CSV_COLUMNS)
    yield _drain()
    for log in rows:
        created = log.created_at.isoformat() if hasattr(log.created_at, "isoformat") else log.created_at
        result = log.result_json if isinstance(getattr(log, "result_json", None), dict) else {}
        writer.writerow([
            log.id, created, log.media_type, csv_safe(log.runway_id),
            # drone_id is client-supplied free text — escape like the other
            # attacker-controlled columns.
            csv_safe(getattr(log, "drone_id", None)),
            log.global_state,
            log.confidence, log.angle_available, log.elevation_angle_deg,
            log.frame_count,
            # Partial-result flags only exist in result_json (no columns); empty
            # cell = complete analysis.
            result.get("truncated_at_frame"), result.get("decode_shortfall"),
            log.processing_ms,
            # Column first, result_json fallback for pre-column rows (audit COL-1).
            # getattr keeps the SimpleNamespace duck-rows in test_csv_export working.
            csv_safe(getattr(log, "model_id", None) or result.get("model_id")),
            csv_safe(result.get("model_label")), csv_safe(result.get("model_role")),
            csv_safe(log.original_filename),
        ])
        yield _drain()
