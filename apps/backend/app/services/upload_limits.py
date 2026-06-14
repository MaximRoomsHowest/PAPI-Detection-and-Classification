"""Shared UploadFile size/count guards for multi-file endpoints."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile


def upload_size_bytes(upload: UploadFile) -> int:
    """Return the spooled upload size without changing its read position."""
    try:
        position = upload.file.tell()
        upload.file.seek(0, 2)
        size = upload.file.tell()
    except (AttributeError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Could not inspect uploaded file size.") from exc
    finally:
        try:
            upload.file.seek(position)
        except (NameError, AttributeError, OSError, ValueError):
            pass
    return size


def enforce_upload_collection_limits(
    files: list[UploadFile],
    settings,
    *,
    what: str,
    count_unit: str = "frames",
) -> None:
    """Enforce request-level count and aggregate-byte limits.

    Per-file caps still live at the streaming save layer. This front-door guard
    prevents multi-file endpoints from accepting hundreds of individually-valid
    files that add up to minutes of work or many gigabytes of transient storage.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one image file.")

    if len(files) > settings.max_batch_frames:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{what} are limited to {settings.max_batch_frames} {count_unit} per "
                f"request. Got {len(files)}. Split the folder and retry, or raise "
                f"PAPI_MAX_BATCH_FRAMES on the server."
            ),
        )

    max_bytes = settings.max_batch_upload_mb * 1024 * 1024
    total = 0
    for upload in files:
        total += upload_size_bytes(upload)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{what} are limited to {settings.max_batch_upload_mb} MB "
                    f"total per request. Split the folder and retry, or raise "
                    f"PAPI_MAX_BATCH_UPLOAD_MB on the server."
                ),
            )
