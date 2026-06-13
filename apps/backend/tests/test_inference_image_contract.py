from types import SimpleNamespace

import numpy as np
from app.config import Settings
from app.services.inference.service import InferenceService
from app.validation.schemas import AngleResult


def test_single_image_model_method_does_not_emit_temporal_transition_state(tmp_path, monkeypatch):
    service = InferenceService(
        Settings(
            storage_dir=tmp_path / "storage",
            model_path=tmp_path / "model.pt",
            model_registry_path=tmp_path / "models.json",
        )
    )
    selected = SimpleNamespace(id="transition", label="Transition classifier", role="transition")
    frame = np.zeros((12, 12, 3), dtype=np.uint8)
    fake_cv2 = SimpleNamespace(
        imread=lambda _path: frame.copy(),
        imwrite=lambda _path, _image: True,
    )

    monkeypatch.setattr(service, "_require_cv2", lambda: fake_cv2)
    monkeypatch.setattr(service, "_resolve_selected_model", lambda _model_id, _method: (object(), selected, "model"))
    monkeypatch.setattr(
        service,
        "_detect_frame",
        lambda _frame, use_tracking, model: [
            {
                "class_id": 2,
                "confidence": 0.9,
                "bbox": {"x1": 1, "y1": 1, "x2": 3, "y2": 3},
            }
        ],
    )
    monkeypatch.setattr(
        service,
        "_angle_for_media",
        lambda *_args, **_kwargs: AngleResult(angle_available=False, angle_note="test"),
    )
    monkeypatch.setattr(service, "_draw_overlay", lambda frame, *_args: frame)
    monkeypatch.setattr(service, "_store_export_artifact", lambda _path: ("artifact", "/media/test.jpg"))

    payload = service.analyze_image(
        tmp_path / "frame.jpg",
        runway_id="papi_24",
        original_filename="frame.jpg",
        drone_id=None,
        drone_metadata=None,
        transition_method="model",
        model_id="transition",
    )

    assert "transition" not in [lamp.state for lamp in payload.lamps]
    assert payload.transitions == []
