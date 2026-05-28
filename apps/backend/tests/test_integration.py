"""TestClient-driven integration tests (audit B-IMP-3).

The existing unit tests cover individual services well, but they never go
through the FastAPI router -- so route wiring, middleware, dependency
injection, and request/response serialisation are uncovered. This file
adds a small set of end-to-end tests that hit the HTTP layer.

Two substitutions in the fixture:

* The DB is replaced with an in-memory SQLite engine + StaticPool for speed
  and isolation. Override via ``app.dependency_overrides[get_session]``.
* The YOLO inference service is replaced with a stub that returns a fixed
  AnalysisPayload (real inference would load ~100 MB of weights and take
  seconds). The route calls ``get_inference_service()`` directly rather
  than via ``Depends``, so we monkeypatch the module-level reference at
  ``app.api.routes.get_inference_service``. Audit follow-up B-IMP-1 would
  refactor the route to use Depends and remove this monkeypatch.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.database import Base, get_session
from app.main import app
from app.services.inference import InferenceService
from app.validation.schemas import (
    AnalysisPayload,
    AngleResult,
    LampResult,
    ModelInfo,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A TestClient with an in-memory DB and a mocked YOLO inference service.

    The inference service is replaced via monkeypatch (not via
    ``app.dependency_overrides``) because the route calls
    ``get_inference_service()`` as a module-level singleton, not as a
    FastAPI dependency. Both substitutions reset cleanly at test teardown.
    """
    # --- DB: in-memory SQLite for speed -------------------------------------
    # ``StaticPool`` + ``check_same_thread=False`` makes every connection
    # share the same underlying in-memory DB. Without it, each request from
    # the TestClient gets a fresh connection -> a fresh empty DB -> the
    # table created in the fixture is invisible. Standard SQLite-in-tests
    # incantation.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    # The analysis_log table needs to exist before the first /api/analyze call.
    from app import models  # noqa: F401 -- registers the AnalysisLog model
    Base.metadata.create_all(bind=engine)

    def override_get_session():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    # --- Inference: a stub that returns a fixed payload ---------------------
    fake_service = MagicMock(spec=InferenceService)

    def _fake_analyze(media_path, media_type, runway_id, original_filename, drone_id=None, drone_metadata=None):
        return AnalysisPayload(
            media_type=media_type,
            original_filename=original_filename,
            runway_id=runway_id,
            drone_id=drone_id,
            global_state="correct_glidepath",
            lamps=[
                LampResult(index=1, state="white", confidence=0.95),
                LampResult(index=2, state="white", confidence=0.94),
                LampResult(index=3, state="red", confidence=0.93),
                LampResult(index=4, state="red", confidence=0.92),
            ],
            confidence=0.935,
            frame_count=1,
            processing_ms=42,
            angle=AngleResult(angle_available=False, angle_note="fixture: no metadata"),
            artifact_url=None,
            detections=[],
        )

    fake_service.analyze.side_effect = _fake_analyze
    fake_service.model_info.return_value = ModelInfo(
        model_path=str(tmp_path / "models" / "best.pt"),
        model_filename="best.pt",
        model_format="pt",
        backend_type="ultralytics-pytorch",
        exists=True,
        file_size_mb=12.5,
        confidence_threshold=0.4,
        device="cpu",
        loaded=False,
    )

    # Override get_session via FastAPI's mechanism (it's a real Depends).
    app.dependency_overrides[get_session] = override_get_session

    # Override get_inference_service at the routes-module call site because
    # the route imports it as a bare function, not via Depends. Audit
    # follow-up B-IMP-1 would refactor the route to use Depends and remove
    # this monkeypatch.
    monkeypatch.setattr(
        "app.api.routes.get_inference_service",
        lambda: fake_service,
    )

    # Storage dirs need to exist so save_upload() can write into them.
    from app.config import get_settings

    get_settings().ensure_storage()

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runways_endpoint_returns_seeded_runways(client):
    response = client.get("/api/runways")
    assert response.status_code == 200

    body = response.json()
    runway_ids = {runway["id"] for runway in body}
    assert {"papi_06", "papi_24"} <= runway_ids
    for runway in body:
        assert len(runway["lights"]) == 4


def test_request_id_header_is_echoed_back(client):
    """RequestIdMiddleware should always set X-Request-ID on responses (audit B-IMP-4)."""
    response = client.get("/health")
    assert response.headers.get("X-Request-ID")


def test_request_id_header_is_preserved_when_client_supplies_one(client):
    """When the caller passes X-Request-ID, the server should propagate it."""
    response = client.get("/health", headers={"X-Request-ID": "test-trace-id-abc"})
    assert response.headers.get("X-Request-ID") == "test-trace-id-abc"


def test_analyze_frame_rejects_video_file(client):
    """``/api/analyze-frame`` is image-only; supplying a video must 400."""
    response = client.post(
        "/api/analyze-frame",
        files={"file": ("clip.mp4", BytesIO(b"\x00" * 16), "video/mp4")},
        data={"runway_id": "papi_24"},
    )
    assert response.status_code == 400
    assert "image" in response.json()["detail"].lower()


def test_analyze_frame_rejects_unknown_media_type(client):
    response = client.post(
        "/api/analyze-frame",
        files={"file": ("notes.txt", BytesIO(b"hello"), "text/plain")},
        data={"runway_id": "papi_24"},
    )
    assert response.status_code == 400


def test_analyze_frame_rejects_unknown_runway(client):
    response = client.post(
        "/api/analyze-frame",
        files={"file": ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={"runway_id": "papi_99"},
    )
    assert response.status_code == 400
    assert "runway" in response.json()["detail"].lower()


def test_analyze_frame_with_partial_drone_metadata_returns_400(client):
    """Either provide all three drone metadata fields or none. Partial = 400."""
    response = client.post(
        "/api/analyze-frame",
        files={"file": ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={
            "runway_id": "papi_24",
            "drone_latitude": "47.674",
            # drone_longitude intentionally omitted
            "drone_altitude_m": "470",
        },
    )
    assert response.status_code == 400


def test_analyze_frame_end_to_end_writes_log_row(client):
    """Happy path: image upload -> mocked inference -> AnalysisPayload + DB row."""
    response = client.post(
        "/api/analyze-frame",
        files={"file": ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={"runway_id": "papi_24"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["global_state"] == "correct_glidepath"
    assert len(body["lamps"]) == 4
    assert body["log_id"]  # repository wrote a row and the id propagated back
    assert body["processing_ms"] == 42


def test_logs_list_and_detail_return_persisted_analysis(client):
    create_response = client.post(
        "/api/analyze-frame",
        files={"file": ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={"runway_id": "papi_24"},
    )
    log_id = create_response.json()["log_id"]

    list_response = client.get("/api/logs")
    assert list_response.status_code == 200
    rows = list_response.json()
    assert rows[0]["id"] == log_id
    assert rows[0]["original_filename"] == "frame.jpg"
    assert rows[0]["global_state"] == "correct_glidepath"

    detail_response = client.get(f"/api/logs/{log_id}")
    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["log_id"] == log_id
    assert body["lamps"][0]["state"] == "white"


def test_model_endpoint_returns_active_model_metadata(client):
    response = client.get("/api/model")

    assert response.status_code == 200
    body = response.json()
    assert body["model_filename"] == "best.pt"
    assert body["backend_type"] == "ultralytics-pytorch"
    assert body["confidence_threshold"] == 0.4
    assert body["device"] == "cpu"


def test_stats_endpoint_summarizes_recent_logs(client):
    for filename in ("first.jpg", "second.jpg"):
        response = client.post(
            "/api/analyze-frame",
            files={"file": (filename, BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
            data={"runway_id": "papi_24"},
        )
        assert response.status_code == 200

    stats_response = client.get("/api/stats")
    assert stats_response.status_code == 200
    body = stats_response.json()
    assert body["sample_size"] == 2
    assert body["image_count"] == 2
    assert body["video_count"] == 0
    assert body["avg_processing_ms"] == 42.0
    assert body["p50_processing_ms"] == 42
    assert body["p95_processing_ms"] == 42
    assert body["latest_created_at"]


def test_analyze_frames_rejects_empty_list(client):
    """Folder upload with no files should fail fast."""
    response = client.post("/api/analyze-frames", files=[], data={"runway_id": "papi_24"})
    # FastAPI returns 422 (validation) when the field is missing entirely,
    # which is also acceptable -- ``files`` is a required parameter.
    assert response.status_code in (400, 422)


def test_analyze_frames_caps_batch_size(client, monkeypatch):
    """Folder uploads above the configured cap return 413, not 200 after a minutes-long loop.

    Regression guard for audit B-MAJ-5: the analyze-frames endpoint
    previously iterated whatever was uploaded, with no upper bound — a
    10,000-image upload would block the worker for minutes. The cap is
    sourced from PAPI_MAX_BATCH_FRAMES so the demo can raise it for
    benchmarking; tests pin it low so the assertion runs fast.
    """
    from app.config import get_settings

    # Lower the cap to 3 for this test so we don't have to construct 200
    # fake JPEGs to trigger the limit.
    get_settings.cache_clear()
    monkeypatch.setenv("PAPI_MAX_BATCH_FRAMES", "3")
    try:
        files = [
            ("files", (f"frame_{i:03d}.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg"))
            for i in range(4)
        ]
        response = client.post(
            "/api/analyze-frames",
            files=files,
            data={"runway_id": "papi_24"},
        )
        assert response.status_code == 413
        body = response.json()
        assert "limited to 3 frames" in body["detail"]
        assert "Got 4" in body["detail"]
    finally:
        # Other tests rely on the default cap; restore.
        get_settings.cache_clear()
