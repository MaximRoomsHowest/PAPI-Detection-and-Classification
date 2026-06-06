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

    def _fake_analyze(
        media_path,
        media_type,
        runway_id,
        original_filename,
        drone_id=None,
        drone_metadata=None,
        drone_samples=None,
    ):
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

    def _fake_analyze_sequence(
        image_paths, runway_id, original_filename, drone_id=None, drone_metadata=None, drone_samples=None
    ):
        return AnalysisPayload(
            media_type="video",
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
            frame_count=len(image_paths),
            processing_ms=99,
            angle=AngleResult(angle_available=False, angle_note="fixture: no metadata"),
            artifact_url="/media/seq_annotated.webm",
            detections=[],
            transitions=[],
        )

    fake_service.analyze.side_effect = _fake_analyze
    fake_service.analyze_frame_sequence.side_effect = _fake_analyze_sequence
    # Readiness gates on the model being loaded; the stub reports loaded by default
    # (test_health_ready_returns_503_when_model_not_loaded flips this).
    fake_service.is_loaded = True
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
    # health_ready lives in app.main and reads get_inference_service() from its own
    # module namespace, so patch it there too (readiness now gates on is_loaded).
    monkeypatch.setattr(
        "app.main.get_inference_service",
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


def test_runways_endpoint_returns_papi06_data_analysis_reference_altitude(client):
    """PAPI 06 uses the data-analysis 461.37 m reference, not the 464.988 m drone floor proxy."""
    response = client.get("/api/runways")
    assert response.status_code == 200

    papi_06 = next(runway for runway in response.json() if runway["id"] == "papi_06")
    altitudes = [light["altitude_m"] for light in papi_06["lights"]]

    assert altitudes == [461.37, 461.37, 461.37, 461.37]
    assert all(altitude != pytest.approx(464.988) for altitude in altitudes)


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


def test_analyze_frame_rejects_oversized_telemetry_file(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("PAPI_MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    try:
        response = client.post(
            "/api/analyze-frame",
            files=[
                ("file", ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")),
                ("metadata_file", ("track.csv", BytesIO(b"x" * (1024 * 1024 + 1)), "text/csv")),
            ],
            data={"runway_id": "papi_24"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 413
    assert "telemetry file exceeds" in response.json()["detail"].lower()


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


def _post_frame(client, runway_id="papi_24"):
    return client.post(
        "/api/analyze-frame",
        files={"file": ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={"runway_id": runway_id},
    )


def test_logs_total_count_header_and_filters(client):
    _post_frame(client)
    _post_frame(client)

    all_logs = client.get("/api/logs")
    assert all_logs.headers.get("X-Total-Count") == "2"
    assert len(all_logs.json()) == 2

    # A runway with no rows -> empty list + zero total.
    empty = client.get("/api/logs", params={"runway_id": "papi_06"})
    assert empty.headers.get("X-Total-Count") == "0"
    assert empty.json() == []

    # Malformed created_after -> 400 (audit IMP-BE-3 validation).
    bad = client.get("/api/logs", params={"created_after": "not-a-date"})
    assert bad.status_code == 400


def test_logs_reject_invalid_filter_values(client):
    invalid_list_filters = [
        {"media_type": "audio"},
        {"global_state": "landed"},
        {"min_confidence": -0.1},
        {"min_confidence": 1.1},
    ]

    for params in invalid_list_filters:
        assert client.get("/api/logs", params=params).status_code == 400

    assert client.get("/api/logs/export.csv", params={"global_state": "landed"}).status_code == 400


def test_logs_accept_zulu_created_after_filter(client):
    response = client.get("/api/logs", params={"created_after": "2026-05-01T12:00:00Z"})
    assert response.status_code == 200


def test_logs_limit_out_of_range_returns_422(client):
    """Page size is validated at the route (Query ge=1, le=100), not silently clamped."""
    assert client.get("/api/logs", params={"limit": 101}).status_code == 422
    assert client.get("/api/logs", params={"limit": 0}).status_code == 422
    assert client.get("/api/logs", params={"offset": -1}).status_code == 422
    assert client.get("/api/logs", params={"limit": 50}).status_code == 200


def test_logs_export_csv(client):
    _post_frame(client)

    response = client.get("/api/logs/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers.get("content-disposition", "")

    text = response.text
    assert "id,created_at,media_type" in text
    assert "correct_glidepath" in text
    assert "frame.jpg" in text


def test_stats_endpoint_aggregates_whole_table(client):
    for _ in range(3):
        _post_frame(client)

    response = client.get("/api/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["total_analyses"] == 3
    assert body["sample_size"] == 3
    assert body["image_count"] == 3
    assert body["by_runway"].get("papi_24") == 3
    assert body["by_global_state"].get("correct_glidepath") == 3
    assert body["by_media_type"].get("image") == 3
    assert body["avg_confidence"] is not None


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


def test_analyze_sequence_caps_batch_size(client, monkeypatch):
    """A sequence upload above the configured cap returns 413, not a minutes-long stitch.

    Sibling guard to test_analyze_frames_caps_batch_size: /api/analyze-sequence
    re-implements the same PAPI_MAX_BATCH_FRAMES check, and the sequence path is
    the heavier one (ByteTrack continuity + WebM stitch), so an accidental removal
    of its cap must fail the suite too.
    """
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PAPI_MAX_BATCH_FRAMES", "3")
    try:
        files = [
            ("files", (f"flight/frame_{i:03d}.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg"))
            for i in range(4)
        ]
        response = client.post(
            "/api/analyze-sequence",
            files=files,
            data={"runway_id": "papi_24"},
        )
        assert response.status_code == 413
        body = response.json()
        assert "Image sequences are limited to 3 frames" in body["detail"]
        assert "Got 4" in body["detail"]
    finally:
        get_settings.cache_clear()


def test_analyze_sequence_returns_single_video_payload(client):
    """A folder of images analysed as a time sequence yields ONE video-type payload
    (not a per-image batch) plus a persisted log row."""
    files = [
        ("files", (f"flight/frame_{i:03d}.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg"))
        for i in range(3)
    ]
    response = client.post("/api/analyze-sequence", files=files, data={"runway_id": "papi_24"})
    assert response.status_code == 200
    body = response.json()
    assert body["media_type"] == "video"
    assert body["frame_count"] == 3
    assert body["original_filename"].endswith("(3 frames)")
    assert body["log_id"]


def test_analyze_sequence_orders_numbered_frames_naturally(client, monkeypatch):
    """frame_10 must not be stitched before frame_2."""
    import app.api.routers.analyze as analyze_router

    saved_names = []

    def fake_save_upload(upload, settings):
        saved_names.append(upload.filename)
        path = settings.uploads_dir / Path(upload.filename.replace("/", "_")).name
        path.write_bytes(b"saved")
        return path

    monkeypatch.setattr(analyze_router, "save_upload", fake_save_upload)

    files = [
        ("files", ("flight/frame_10.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")),
        ("files", ("flight/frame_2.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")),
        ("files", ("flight/frame_1.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")),
    ]

    response = client.post("/api/analyze-sequence", files=files, data={"runway_id": "papi_24"})

    assert response.status_code == 200
    assert saved_names == ["flight/frame_1.jpg", "flight/frame_2.jpg", "flight/frame_10.jpg"]


def test_analyze_sequence_rejects_empty_list(client):
    response = client.post("/api/analyze-sequence", files=[], data={"runway_id": "papi_24"})
    assert response.status_code in (400, 422)


def test_analyze_sequence_rejects_video_file(client):
    """The sequence endpoint is image-only; a video among the files is a 400."""
    files = [("files", ("clip.mp4", BytesIO(b"\x00" * 16), "video/mp4"))]
    response = client.post("/api/analyze-sequence", files=files, data={"runway_id": "papi_24"})
    assert response.status_code == 400


def test_health_ready_reports_dependencies(client):
    """Deep readiness probe is 200 when the DB is reachable and the model is loaded."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["model_loaded"] is True


def test_health_ready_returns_503_when_model_not_loaded(client, monkeypatch):
    """A backend whose weights failed to load must report not-ready (503), not 200.

    Regression guard: readiness previously checked only DB + model-file-present, so a
    broken/unloaded checkpoint still returned 200 and traffic was routed to an instance
    that 503s on the first real inference.
    """
    from types import SimpleNamespace

    monkeypatch.setattr("app.main.get_inference_service", lambda: SimpleNamespace(is_loaded=False))
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["model_loaded"] is False


def test_system_endpoint_returns_runtime_facts(client):
    response = client.get("/api/system")
    assert response.status_code == 200
    body = response.json()
    assert body["platform"]
    assert body["python_version"]
    assert "device_configured" in body
    assert body["app_version"]


def test_analyze_frame_rejects_out_of_range_latitude(client):
    """Audit IMP-BE-10: out-of-range geo inputs are rejected, not fed to the angle math."""
    response = client.post(
        "/api/analyze-frame",
        files={"file": ("frame.jpg", BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")},
        data={
            "runway_id": "papi_24",
            "drone_latitude": "999",
            "drone_longitude": "9.5",
            "drone_altitude_m": "470",
        },
    )
    assert response.status_code == 400
    assert "latitude" in response.json()["detail"].lower()
