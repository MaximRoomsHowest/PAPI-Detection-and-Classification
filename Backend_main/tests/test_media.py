import pytest

from app.services.media import detect_media_type


def test_detect_media_type_from_extension():
    assert detect_media_type("frame.jpg", None) == "image"
    assert detect_media_type("clip.mp4", None) == "video"


def test_detect_media_type_rejects_unknown_files():
    with pytest.raises(ValueError):
        detect_media_type("notes.txt", "text/plain")

