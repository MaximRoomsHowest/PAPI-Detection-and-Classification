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
