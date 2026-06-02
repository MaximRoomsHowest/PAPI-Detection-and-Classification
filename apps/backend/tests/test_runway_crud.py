"""POST/DELETE /api/runways: register a runway the model can actually score
against, then remove it. Plus FramePoint / AnalysisPayload.per_frame coverage.

The custom-runway store persists to a JSON sidecar under the backend storage dir
and caches in a module global, so each test isolates both (a throwaway tmp file +
an empty in-memory cache) to avoid polluting apps/backend/storage or leaking a
registered runway into the other suites running in the same process.
"""

from __future__ import annotations

from io import BytesIO

import pytest

import app.services.runways as runways
from app.validation.schemas import AnalysisPayload, AngleResult, FramePoint
from test_integration import client  # noqa: F401  (reused pytest fixture: mocked inference + in-memory DB)


@pytest.fixture
def isolated_runways(tmp_path, monkeypatch):
    store_path = tmp_path / "custom_runways.json"
    monkeypatch.setattr(runways, "_custom_cache", {})
    monkeypatch.setattr(runways, "_custom_path", lambda: store_path)
    yield store_path
    # Reset so a later test in the same process re-reads from its own (real) path.
    runways._custom_cache = None


def _valid_lights() -> list[dict]:
    # Four distinct lamp positions (a real PAPI row spans a few metres).
    return [
        {"point": 1, "latitude": 47.67352, "longitude": 9.51815, "altitude_m": 461.0},
        {"point": 2, "latitude": 47.67345, "longitude": 9.51821, "altitude_m": 461.0},
        {"point": 3, "latitude": 47.67338, "longitude": 9.51827, "altitude_m": 461.0},
        {"point": 4, "latitude": 47.67331, "longitude": 9.51833, "altitude_m": 461.0},
    ]


def test_create_runway_is_listed_usable_and_deletable(client, isolated_runways):
    # --- create -------------------------------------------------------------
    created = client.post(
        "/api/runways",
        json={"label": "Test PAPI 33", "designation": "33", "airport": "TEST", "lights": _valid_lights()},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    runway_id = body["id"]
    assert runway_id.startswith("custom_")  # namespaced so it can't collide with papi_*
    assert body["source"] == "custom"
    assert body["airport"] == "TEST"
    assert len(body["lights"]) == 4
    # Sidecar file was written so the runway survives a restart.
    assert isolated_runways.exists()

    # --- appears in the list alongside the built-ins ------------------------
    listed = client.get("/api/runways").json()
    ids = {r["id"] for r in listed}
    assert runway_id in ids
    assert {"papi_06", "papi_24"} <= ids  # built-ins untouched

    # --- usable for analysis (reaches inference -> 200, not a 400 reject) ----
    analyze = client.post(
        "/api/analyze-frame",
        files={"file": ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={"runway_id": runway_id},
    )
    assert analyze.status_code == 200
    assert analyze.json()["runway_id"] == runway_id

    # --- delete -------------------------------------------------------------
    assert client.delete(f"/api/runways/{runway_id}").status_code == 204
    assert runway_id not in {r["id"] for r in client.get("/api/runways").json()}


def test_create_runway_rejects_wrong_lamp_count(client, isolated_runways):
    resp = client.post("/api/runways", json={"label": "Bad", "lights": _valid_lights()[:3]})
    assert resp.status_code == 422


def test_create_runway_rejects_out_of_range_coordinate(client, isolated_runways):
    bad = _valid_lights()
    bad[0]["latitude"] = 999.0  # outside [-90, 90]
    resp = client.post("/api/runways", json={"label": "Bad", "lights": bad})
    assert resp.status_code == 422


def test_delete_builtin_runway_is_forbidden(client, isolated_runways):
    resp = client.delete("/api/runways/papi_24")
    assert resp.status_code == 400
    assert "built-in" in resp.json()["detail"].lower()


def test_delete_unknown_runway_is_404(client, isolated_runways):
    assert client.delete("/api/runways/custom_does_not_exist").status_code == 404


def test_frame_point_and_per_frame_contract():
    base = dict(
        media_type="video",
        original_filename="clip.webm",
        runway_id="papi_24",
        global_state="unknown",
        lamps=[],
        confidence=0.5,
        frame_count=2,
        processing_ms=10,
        angle=AngleResult(angle_available=False, angle_note="no metadata"),
    )
    # Defaults to empty (single images / back-compat).
    assert AnalysisPayload(**base).per_frame == []
    # Accepts a real per-frame series.
    payload = AnalysisPayload(
        **base,
        per_frame=[FramePoint(frame_index=0, confidence=0.91, state="correct_glidepath")],
    )
    assert payload.per_frame[0].frame_index == 0
    # confidence is a probability in [0, 1].
    with pytest.raises(Exception):
        FramePoint(frame_index=0, confidence=1.5, state="unknown")
