"""runway_id validation across the analyze endpoints (audit B-CRIT/_runways).

``validate_runway_id`` is meant to reject an unknown runway with HTTP 400
*before* any inference runs (and before any upload is written to disk). The
existing test_integration suite asserts the 400 for /analyze-frame; this file
additionally pins:

  * the rejection happens BEFORE the inference service is touched (the stub's
    analyze / analyze_frame_sequence must not be called), and
  * /analyze-sequence enforces the same rule, and
  * a known runway still reaches inference and succeeds.

Reuses the ``client`` fixture from test_integration, which monkeypatches a
MagicMock inference service so call counts are observable.
"""

from __future__ import annotations

from io import BytesIO

import app.api.routes as routes
from test_integration import client  # noqa: F401  (pytest fixture)


def _image_files(field="file", name="frame.jpg"):
    return {field: (name, BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg")}


def _seq_files(name="flight/frame_000.jpg"):
    return [("files", (name, BytesIO(b"\xff\xd8\xff" + b"\x00" * 256), "image/jpeg"))]


def test_analyze_frame_unknown_runway_rejected_before_inference(client):
    service = routes.get_inference_service()  # the stub installed by the fixture
    service.analyze.reset_mock()

    response = client.post(
        "/api/analyze-frame",
        files=_image_files(),
        data={"runway_id": "papi_does_not_exist"},
    )

    assert response.status_code == 400
    assert "runway" in response.json()["detail"].lower()
    # The guard fired up front: inference was never invoked.
    service.analyze.assert_not_called()


def test_analyze_sequence_unknown_runway_rejected_before_inference(client):
    service = routes.get_inference_service()
    service.analyze_frame_sequence.reset_mock()

    response = client.post(
        "/api/analyze-sequence",
        files=_seq_files(),
        data={"runway_id": "papi_does_not_exist"},
    )

    assert response.status_code == 400
    assert "runway" in response.json()["detail"].lower()
    service.analyze_frame_sequence.assert_not_called()


def test_analyze_frame_known_runway_reaches_inference(client):
    service = routes.get_inference_service()
    service.analyze.reset_mock()

    response = client.post(
        "/api/analyze-frame",
        files=_image_files(),
        data={"runway_id": "papi_06"},
    )

    assert response.status_code == 200
    assert service.analyze.call_count == 1
    assert response.json()["runway_id"] == "papi_06"


def test_analyze_sequence_known_runway_reaches_inference(client):
    service = routes.get_inference_service()
    service.analyze_frame_sequence.reset_mock()

    response = client.post(
        "/api/analyze-sequence",
        files=_seq_files(),
        data={"runway_id": "papi_24"},
    )

    assert response.status_code == 200
    assert service.analyze_frame_sequence.call_count == 1
    assert response.json()["runway_id"] == "papi_24"
