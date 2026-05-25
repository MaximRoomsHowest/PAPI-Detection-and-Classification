from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import Settings


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def detect_media_type(filename: str, content_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS or (content_type or "").startswith("image/"):
        return "image"
    if suffix in VIDEO_EXTENSIONS or (content_type or "").startswith("video/"):
        return "video"
    raise ValueError("Unsupported media type. Upload an image or video file.")


def safe_upload_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"{uuid4()}{suffix}"


async def save_upload(upload: UploadFile, settings: Settings) -> Path:
    target = settings.uploads_dir / safe_upload_name(upload.filename or "upload")
    with target.open("wb") as output:
        while chunk := await upload.read(1024 * 1024):
            output.write(chunk)
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

