import json

import pytest
from app.config import Settings
from app.services.inference import InferenceService


def test_video_frame_limit_uses_lower_frame_or_duration_cap(tmp_path):
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
        max_video_frames=600,
        max_video_seconds=10,
    )
    service = InferenceService(settings)

    assert service._video_frame_limit(30) == 300
    assert service._video_frame_limit(90) == 600


def test_model_info_detects_onnx_backend_without_loading_model(tmp_path):
    model_path = tmp_path / "models" / "best_int8.onnx"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"onnx fixture")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=model_path,
        confidence_threshold=0.55,
    )

    info = InferenceService(settings).model_info()

    assert info.model_filename == "best_int8.onnx"
    assert info.model_format == "onnx"
    assert info.backend_type == "ultralytics-onnxruntime"
    assert info.exists is True
    assert info.loaded is False
    assert info.confidence_threshold == 0.55
    assert info.device == "cpu"


def test_model_info_surfaces_weather_metrics_from_card(tmp_path):
    """Per-condition weather robustness in the model card reaches /api/model unparsed."""
    model_path = tmp_path / "models" / "best.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"pt fixture")
    (model_path.parent / "model_card.json").write_text(
        json.dumps(
            {
                "weather_metrics": {
                    "severity": "medium",
                    "split": "test",
                    "clear": 0.95,
                    "rain": 0.94,
                    "fog": 0.93,
                    "haze": 0.92,
                    "snow": 0.88,
                }
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(storage_dir=tmp_path / "storage", model_path=model_path)

    info = InferenceService(settings).model_info()

    assert info.weather_metrics is not None
    assert info.weather_metrics.severity == "medium"
    assert info.weather_metrics.split == "test"
    assert info.weather_metrics.clear == 0.95
    assert info.weather_metrics.snow == 0.88


def test_pixel_budget_rejects_oversized_frame(tmp_path):
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
        max_image_megapixels=1,
    )
    service = InferenceService(settings)

    # 1000x1000 = 1.0 MP sits exactly at the 1 MP cap -> allowed.
    service._check_pixel_budget(1000, 1000, "image")
    # A non-positive dimension means "unknown" (cv2 CAP_PROP can return 0) -> allowed.
    service._check_pixel_budget(0, 0, "video frame")
    # 2000x2000 = 4 MP exceeds the cap -> rejected.
    with pytest.raises(ValueError, match="too large to decode"):
        service._check_pixel_budget(2000, 2000, "image")
