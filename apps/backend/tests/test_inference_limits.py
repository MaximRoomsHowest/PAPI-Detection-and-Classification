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
