"""CSV export coverage for /api/logs/export.csv and the _csv helpers.

The existing test_integration::test_logs_export_csv covers the happy-path
header + a couple of cell values. This file pins the things that file does
not: the exact header column order, the formula-injection guard
(``csv_safe``) on both attacker-controlled columns, and that the export
respects the same filters as /api/logs.

The HTTP tests reuse the ``client`` fixture from test_integration (in-memory
DB + mocked inference). The injection guard is also exercised directly at the
unit level for ``runway_id`` — that column is validated against the known
runway set on the write path, so it can't be poisoned through the HTTP API;
the defensive escape is verified by feeding ``stream_log_rows`` a crafted row.
"""

from __future__ import annotations

import csv
import io
from io import BytesIO
from types import SimpleNamespace

from app.api._csv import CSV_COLUMNS, csv_safe, stream_log_rows

# Reuse the configured TestClient fixture (in-memory DB + stubbed inference).
from test_integration import client  # noqa: F401

# --- unit: csv_safe -------------------------------------------------------


def test_csv_safe_neutralises_formula_leading_characters():
    """A cell whose FIRST char is = + - @ (or a control char) is forced to a
    literal with a leading apostrophe so it can't execute in a spreadsheet."""
    assert csv_safe("=cmd()") == "'=cmd()"
    assert csv_safe("+1+1") == "'+1+1"
    assert csv_safe("-2+3") == "'-2+3"
    assert csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert csv_safe("\tTAB") == "'\tTAB"
    assert csv_safe("\rCR") == "'\rCR"
    assert csv_safe("\nLF") == "'\nLF"


def test_csv_safe_leaves_benign_values_untouched():
    """Only the leading character matters; interior =/+/-/@ are safe."""
    assert csv_safe("frame.jpg") == "frame.jpg"
    assert csv_safe("papi_24") == "papi_24"
    assert csv_safe("a=b+c") == "a=b+c"
    # None / empty render as empty string, never an apostrophe.
    assert csv_safe(None) == ""
    assert csv_safe("") == ""


# --- unit: stream_log_rows ------------------------------------------------


def _crafted_log():
    """A log-row stand-in (duck-typed) with injection payloads in BOTH
    attacker-controlled free-text columns."""
    return SimpleNamespace(
        id="row-1",
        created_at=SimpleNamespace(isoformat=lambda: "2026-06-02T10:00:00"),
        media_type="image",
        runway_id="=HYPERLINK(0)",  # defensively escaped even though validated on write
        global_state="correct_glidepath",
        confidence=0.9,
        angle_available=False,
        elevation_angle_deg=None,
        frame_count=1,
        processing_ms=42,
        result_json={"model_id": "small", "model_label": "Small detector", "model_role": "detector"},
        original_filename="@evil.jpg",
    )


def test_stream_log_rows_header_matches_column_constant():
    body = "".join(stream_log_rows([]))
    reader = list(csv.reader(io.StringIO(body)))
    assert reader[0] == CSV_COLUMNS
    # Sanity-pin the documented order so a reorder is a visible diff.
    assert CSV_COLUMNS[:6] == ["id", "created_at", "media_type", "runway_id", "drone_id", "global_state"]
    assert "truncated_at_frame" in CSV_COLUMNS
    assert "decode_shortfall" in CSV_COLUMNS
    assert CSV_COLUMNS[-4:-1] == ["model_id", "model_label", "model_role"]
    assert CSV_COLUMNS[-1] == "original_filename"


def test_stream_log_rows_exports_model_metadata_from_result_json():
    body = "".join(stream_log_rows([_crafted_log()]))
    rows = list(csv.reader(io.StringIO(body)))
    data = rows[1]
    assert data[CSV_COLUMNS.index("model_id")] == "small"
    assert data[CSV_COLUMNS.index("model_label")] == "Small detector"
    assert data[CSV_COLUMNS.index("model_role")] == "detector"


def test_stream_log_rows_exports_partial_result_flags_and_drone_id():
    """truncated_at_frame / decode_shortfall live only in result_json and
    drone_id was documented as a CSV provenance column but never exported —
    a partial analysis was indistinguishable from a complete one in the CSV
    (audit 2026-06-12)."""
    log = _crafted_log()
    log.drone_id = "=DRONE-7"  # client-supplied free text -> must be escaped
    log.result_json = {**log.result_json, "truncated_at_frame": 120, "decode_shortfall": 30}

    body = "".join(stream_log_rows([log]))
    data = list(csv.reader(io.StringIO(body)))[1]

    assert data[CSV_COLUMNS.index("drone_id")] == "'=DRONE-7"
    assert data[CSV_COLUMNS.index("truncated_at_frame")] == "120"
    assert data[CSV_COLUMNS.index("decode_shortfall")] == "30"
    # A complete analysis leaves both flag cells empty, not "None".
    complete = "".join(stream_log_rows([_crafted_log()]))
    complete_row = list(csv.reader(io.StringIO(complete)))[1]
    assert complete_row[CSV_COLUMNS.index("truncated_at_frame")] == ""
    assert complete_row[CSV_COLUMNS.index("decode_shortfall")] == ""
    assert complete_row[CSV_COLUMNS.index("drone_id")] == ""


def test_stream_log_rows_escapes_both_freetext_columns():
    body = "".join(stream_log_rows([_crafted_log()]))
    rows = list(csv.reader(io.StringIO(body)))
    # csv.reader strips the field quoting but preserves the literal apostrophe
    # that csv_safe prepended.
    data = rows[1]
    runway_id = data[CSV_COLUMNS.index("runway_id")]
    filename = data[CSV_COLUMNS.index("original_filename")]
    assert runway_id == "'=HYPERLINK(0)"
    assert filename == "'@evil.jpg"


# --- HTTP: end-to-end export ---------------------------------------------


def _post_frame(client, filename="frame.jpg", runway_id="papi_24"):
    return client.post(
        "/api/analyze-frame",
        files={"file": (filename, BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={"runway_id": runway_id},
    )


def test_export_csv_header_order_over_http(client):
    _post_frame(client)
    response = client.get("/api/logs/export.csv")
    assert response.status_code == 200

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == CSV_COLUMNS


def test_export_csv_neutralises_crafted_filename_over_http(client):
    """A crafted upload name that starts with '=' must arrive in the CSV with a
    protective leading apostrophe — the full injection path, upload -> log -> export."""
    # ``.jpg`` suffix keeps it a valid image; the stem carries the payload.
    assert _post_frame(client, filename="=cmd()|calc.jpg").status_code == 200

    response = client.get("/api/logs/export.csv")
    assert response.status_code == 200

    rows = list(csv.reader(io.StringIO(response.text)))
    filenames = [r[CSV_COLUMNS.index("original_filename")] for r in rows[1:]]
    assert "'=cmd()|calc.jpg" in filenames
    # The raw, unescaped form must NOT appear as a cell value.
    assert "=cmd()|calc.jpg" not in filenames


def test_export_csv_respects_runway_filter(client):
    """Export honours the same filters as /api/logs (audit IMP-BE-6)."""
    _post_frame(client, filename="keep.jpg", runway_id="papi_24")

    # Filter to a runway that has no rows -> header only, no data lines.
    filtered = client.get("/api/logs/export.csv", params={"runway_id": "papi_06"})
    assert filtered.status_code == 200
    rows = list(csv.reader(io.StringIO(filtered.text)))
    assert rows[0] == CSV_COLUMNS
    assert len(rows) == 1  # header only

    # Filtering to the populated runway returns the row.
    kept = client.get("/api/logs/export.csv", params={"runway_id": "papi_24"})
    kept_rows = list(csv.reader(io.StringIO(kept.text)))
    assert len(kept_rows) == 2  # header + 1
    assert kept_rows[1][CSV_COLUMNS.index("original_filename")] == "keep.jpg"
