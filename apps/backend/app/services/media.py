from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import Settings
from app.services.storage import get_media_storage, media_url_for_reference

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
GENERIC_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}
_PEEK_BYTES = 512


def detect_media_type(filename: str, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    normalized_content_type = (content_type or "").split(";", 1)[0].lower()
    is_image_extension = suffix in IMAGE_EXTENSIONS
    is_video_extension = suffix in VIDEO_EXTENSIONS
    is_image_content = normalized_content_type.startswith("image/")
    is_video_content = normalized_content_type.startswith("video/")

    if is_image_extension and (not normalized_content_type or is_image_content or normalized_content_type in GENERIC_CONTENT_TYPES):
        return "image"
    if is_video_extension and (not normalized_content_type or is_video_content or normalized_content_type in GENERIC_CONTENT_TYPES):
        return "video"
    if not suffix and is_image_content:
        return "image"
    if not suffix and is_video_content:
        return "video"
    if (is_image_extension and is_video_content) or (is_video_extension and is_image_content):
        raise ValueError("File extension does not match the uploaded media type.")
    raise ValueError("Unsupported media type. Upload an image or video file.")


def safe_upload_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"{uuid4()}{suffix}"


def validate_media_signature(upload: UploadFile, media_type: str) -> None:
    """Validate the upload's magic bytes without consuming the stream.

    Extension and content-type checks are useful routing hints, but they are both
    caller-controlled. This rejects obvious polyglot/mislabeled payloads before
    they reach OpenCV's image/video decoders.
    """
    try:
        position = upload.file.tell()
        header = upload.file.read(_PEEK_BYTES)
    except (AttributeError, OSError, ValueError) as exc:
        raise ValueError("Could not inspect uploaded file signature.") from exc
    finally:
        try:
            upload.file.seek(position)
        except (NameError, AttributeError, OSError, ValueError):
            pass

    if media_type == "image" and _looks_like_image(header):
        return
    if media_type == "video" and _looks_like_video(header):
        return
    raise ValueError(f"Uploaded {media_type} does not match a supported file signature.")


def _looks_like_image(header: bytes) -> bool:
    return (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"BM")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )


def _looks_like_video(header: bytes) -> bool:
    return (
        header[4:8] == b"ftyp"  # mp4/mov/quicktime family
        or header.startswith(b"\x1a\x45\xdf\xa3")  # webm/mkv EBML
        or (header.startswith(b"RIFF") and header[8:12] == b"AVI ")
    )


def save_upload(upload: UploadFile, settings: Settings) -> Path:
    """Stream the upload to disk in chunks, enforcing the size cap.

    Synchronous on purpose: the analyze endpoints are plain ``def`` so FastAPI
    runs them in its threadpool, where blocking reads/writes are fine and do not
    stall the event loop. Reads ``upload.file`` (the underlying SpooledTemporaryFile)
    directly instead of the async ``await upload.read``.
    """
    target = settings.uploads_dir / safe_upload_name(upload.filename or "upload")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    bytes_written = 0
    try:
        with target.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise ValueError(f"Upload exceeds the {settings.max_upload_mb} MB limit.")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    try:
        get_media_storage(settings).persist_upload(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def media_url_for_path(path: str | None, settings: Settings) -> str | None:
    return media_url_for_reference(path, settings)
