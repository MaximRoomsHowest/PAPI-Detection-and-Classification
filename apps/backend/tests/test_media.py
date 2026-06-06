from io import BytesIO

import pytest
from app.config import Settings
from app.services.media import (
    detect_media_type,
    media_url_for_path,
    save_upload,
    validate_media_signature,
)
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


def test_validate_media_signature_accepts_known_image_header():
    upload = UploadFile(filename="frame.jpg", file=BytesIO(b"\xff\xd8\xff\xe0" + b"x" * 64))

    validate_media_signature(upload, "image")

    assert upload.file.tell() == 0


def test_validate_media_signature_restores_nonzero_stream_position():
    upload = UploadFile(filename="frame.jpg", file=BytesIO(b"prefix" + b"\xff\xd8\xff\xe0" + b"x" * 64))
    upload.file.seek(6)

    validate_media_signature(upload, "image")

    assert upload.file.tell() == 6


def test_validate_media_signature_rejects_mislabeled_image():
    upload = UploadFile(filename="frame.jpg", file=BytesIO(b"<script>alert(1)</script>"))

    with pytest.raises(ValueError, match="supported file signature"):
        validate_media_signature(upload, "image")

    assert upload.file.tell() == 0


def test_validate_media_signature_accepts_mp4_family_header():
    upload = UploadFile(filename="clip.mp4", file=BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64))

    validate_media_signature(upload, "video")

    assert upload.file.tell() == 0


def test_media_url_for_path_requires_exports_dir(tmp_path):
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
    )
    settings.ensure_storage()

    assert media_url_for_path(str(settings.exports_dir / "clip.webm"), settings) == "/media/clip.webm"
    assert media_url_for_path(str(settings.uploads_dir / "clip.webm"), settings) is None
    assert media_url_for_path(str(settings.exports_dir / ".." / "uploads" / "clip.webm"), settings) is None

