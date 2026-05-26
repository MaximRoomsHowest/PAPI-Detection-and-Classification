from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import Settings

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
GENERIC_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}


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


async def save_upload(upload: UploadFile, settings: Settings) -> Path:
    target = settings.uploads_dir / safe_upload_name(upload.filename or "upload")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    bytes_written = 0
    try:
        with target.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise ValueError(f"Upload exceeds the {settings.max_upload_mb} MB limit.")
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def media_url_for_path(path: str | None, settings: Settings) -> str | None:
    if not path:
        return None
    artifact = Path(path)
    try:
        relative = artifact.relative_to(settings.exports_dir)
    except ValueError:
        return None
    return f"/media/{relative.as_posix()}"

