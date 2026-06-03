"""Edge cases for detect_media_type (app.services.media).

test_media.py covers the three common cases (extension-only image/video, a
text file rejected, and a jpg-with-video content-type mismatch). This file
pins the trickier branches that the production uploads actually exercise —
browsers and drone exporters frequently send ``application/octet-stream`` or
omit the extension — plus both directions of the ext/content-type mismatch.

Branch map (from media.detect_media_type):
  * image extension + generic octet-stream            -> "image"
  * video extension + generic octet-stream            -> "video"
  * no extension + image content-type                 -> "image"
  * no extension + video content-type                 -> "video"
  * content-type carrying a ``;charset`` param         -> param stripped, matched
  * image extension + video content-type (mismatch)   -> ValueError("does not match")
  * video extension + image content-type (mismatch)   -> ValueError("does not match")
  * no extension + no/garbage content-type            -> ValueError("Unsupported")
  * no extension + generic octet-stream               -> ValueError (octet only
    rescues a KNOWN extension, it cannot stand in for a missing one)
"""

from __future__ import annotations

import pytest
from app.services.media import detect_media_type

# --- generic octet-stream rescues a known extension -----------------------


def test_octet_stream_with_image_extension_is_image():
    assert detect_media_type("frame.jpg", "application/octet-stream") == "image"
    assert detect_media_type("frame.png", "binary/octet-stream") == "image"


def test_octet_stream_with_video_extension_is_video():
    assert detect_media_type("clip.mp4", "application/octet-stream") == "video"


# --- no extension, decided by content-type --------------------------------


def test_no_extension_image_content_type_is_image():
    assert detect_media_type("frame", "image/png") == "image"


def test_no_extension_video_content_type_is_video():
    assert detect_media_type("capture", "video/mp4") == "video"


# --- content-type parameter is stripped before matching -------------------


def test_content_type_with_charset_parameter_is_handled():
    assert detect_media_type("frame.png", "image/png; charset=binary") == "image"


# --- mismatched extension vs content-type (both directions) ---------------


def test_image_extension_with_video_content_type_raises():
    with pytest.raises(ValueError, match="does not match"):
        detect_media_type("frame.jpg", "video/mp4")


def test_video_extension_with_image_content_type_raises():
    with pytest.raises(ValueError, match="does not match"):
        detect_media_type("clip.mp4", "image/png")


# --- genuinely undecidable inputs reject ----------------------------------


def test_no_extension_and_no_content_type_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        detect_media_type("frame", None)


def test_no_extension_with_only_octet_stream_raises():
    """octet-stream cannot substitute for a MISSING extension — it only relaxes
    the content-type check for a file that already has a known suffix."""
    with pytest.raises(ValueError, match="Unsupported"):
        detect_media_type("blob", "application/octet-stream")
