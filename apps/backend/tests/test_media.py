from io import BytesIO

import pytest
from app.config import Settings
from app.services.media import detect_media_type, media_url_for_path, save_upload
from starlette.datastructures import UploadFile


def test_detect_media_type_from_extension():
    assert detect_media_type("frame.jpg", None) == "image"
    assert detect_media_type("clip.mp4", None) == "video"


def test_detect_media_type_rejects_unknown_files():
    with pytest.raises(ValueError):
        detect_media_type("notes.txt", "text/plain")


def test_detect_media_type_rejects_mismatched_content_type():
    with pytest.raises(ValueError, match="does not match"):
        detect_media_type("frame.jpg", "video/mp4")


def test_save_upload_enforces_size_limit(tmp_path):
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
        max_upload_mb=1,
    )
    settings.ensure_storage()
    upload = UploadFile(filename="large.jpg", file=BytesIO(b"x" * (1024 * 1024 + 1)))

    with pytest.raises(ValueError, match="Upload exceeds"):
        save_upload(upload, settings)

    assert list(settings.uploads_dir.iterdir()) == []


def test_media_url_for_path_requires_exports_dir(tmp_path):
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
    )
    settings.ensure_storage()

    assert media_url_for_path(str(settings.exports_dir / "clip.webm"), settings) == "/media/clip.webm"
    assert media_url_for_path(str(settings.uploads_dir / "clip.webm"), settings) is None
    assert media_url_for_path(str(settings.exports_dir / ".." / "uploads" / "clip.webm"), settings) is None

