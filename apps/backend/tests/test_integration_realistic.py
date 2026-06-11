"""Round-trip integration tests with realistic inference payloads.

test_integration.py pins route wiring with a minimal fixed payload; these tests
use tests/realistic_inference.py to push the parts of the video contract the
frontend actually renders — per_frame, transitions, truncated_at_frame, and
tracked detections — through the real HTTP layer + DB persistence + CSV export.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from app.database import Base, get_session
from app.main import app
from fastapi.testclient import TestClient
from realistic_inference import make_realistic_inference_service
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

JPEG = b"\xff\xd8\xff" + b"\x00" * 256
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 256


@pytest.fixture
def make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Factory: a TestClient whose inference stub is the realistic fake.

    ``video_kwargs`` forward to realistic_video_payload (e.g. truncated=True),
    so a test can shape the video contract it wants to round-trip. Same DB and
    monkeypatch substitutions as test_integration.py's fixture.
    """

    def _make(**video_kwargs) -> TestClient:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        session_local = sessionmaker(
            bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
        from app import models  # noqa: F401 -- registers the AnalysisLog model

        Base.metadata.create_all(bind=engine)

        def override_get_session():
            db = session_local()
            try:
                yield db
            finally:
                db.close()

        fake_service = make_realistic_inference_service(tmp_path, **video_kwargs)
        app.dependency_overrides[get_session] = override_get_session
        monkeypatch.setattr("app.api.routes.get_inference_service", lambda: fake_service)
        monkeypatch.setattr("app.main.get_inference_service", lambda: fake_service)

        from app.config import get_settings

        get_settings().ensure_storage()
        return TestClient(app)

    yield _make
    app.dependency_overrides.clear()


def test_video_contract_round_trips_through_http(make_client):
    client = make_client(with_transitions=True, with_angle_track=True, frame_count=48)

    response = client.post(
        "/api/analyze",
        files={"file": ("approach.mp4", BytesIO(MP4), "video/mp4")},
        data={"runway_id": "papi_24"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["media_type"] == "video"
    assert body["frame_count"] == 48
    assert len(body["per_frame"]) == 48
    # The deterministic dips must survive serialisation as real unknown frames.
    unknown_frames = [point for point in body["per_frame"] if point["state"] == "unknown"]
    assert len(unknown_frames) == 2
    assert body["transition_method"] == "tracking"
    assert body["transitions"][0]["lamp_index"] == 2
    assert body["transitions"][0]["from_state"] == "red"
    assert body["transitions"][0]["to_state"] == "white"
    assert body["angle"]["angle_available"] is True
    assert body["angle_track"], "angle_track must survive the HTTP layer"
    assert body["log_id"]


def test_truncated_video_persists_and_reloads(make_client):
    client = make_client(truncated=True, frame_count=600)

    response = client.post(
        "/api/analyze",
        files={"file": ("long.mp4", BytesIO(MP4), "video/mp4")},
        data={"runway_id": "papi_24"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["truncated_at_frame"] == 600

    # The truncation stamp must survive DB persistence and the detail reload —
    # History renders the honesty banner from this field.
    detail = client.get(f"/api/logs/{body['log_id']}")
    assert detail.status_code == 200
    assert detail.json()["truncated_at_frame"] == 600
    assert detail.json()["frame_count"] == 600


def test_tracked_detections_survive_the_log_round_trip(make_client):
    client = make_client()

    response = client.post(
        "/api/analyze",
        files={"file": ("approach.mp4", BytesIO(MP4), "video/mp4")},
        data={"runway_id": "papi_24"},
    )
    assert response.status_code == 200
    log_id = response.json()["log_id"]

    detail = client.get(f"/api/logs/{log_id}").json()
    detections = detail["detections"]
    assert len(detections) == 4
    # Tracked video detections carry stable ByteTrack ids and pixel boxes.
    assert [detection["track_id"] for detection in detections] == [1, 2, 3, 4]
    for detection in detections:
        bbox = detection["bbox"]
        assert bbox["x2"] >= bbox["x1"] and bbox["y2"] >= bbox["y1"]
    # Lamp states and classes line up (white=1, red=0, left to right).
    assert [detection["class_id"] for detection in detections] == [1, 1, 0, 0]


def test_stats_endpoint_applies_the_shared_filters(make_client):
    client = make_client()

    analyzed = client.post(
        "/api/analyze",
        files={"file": ("frame.jpg", BytesIO(JPEG), "image/jpeg")},
        data={"runway_id": "papi_24"},
    )
    assert analyzed.status_code == 200

    matching = client.get("/api/stats", params={"runway_id": "papi_24"}).json()
    assert matching["total_analyses"] == 1
    assert matching["by_runway"] == {"papi_24": 1}

    other = client.get("/api/stats", params={"runway_id": "papi_06"}).json()
    assert other["total_analyses"] == 0

    # Malformed filters are rejected like /api/logs, not silently zeroed.
    invalid = client.get("/api/stats", params={"global_state": "bogus"})
    assert invalid.status_code == 400


def test_csv_export_contains_the_realistic_row(make_client):
    client = make_client()

    analyzed = client.post(
        "/api/analyze",
        files={"file": ("frame.jpg", BytesIO(JPEG), "image/jpeg")},
        data={"runway_id": "papi_24"},
    )
    assert analyzed.status_code == 200

    export = client.get("/api/logs/export.csv")
    assert export.status_code == 200
    csv_text = export.text
    assert "frame.jpg" in csv_text
    assert "correct_glidepath" in csv_text
    assert "papi_24" in csv_text
