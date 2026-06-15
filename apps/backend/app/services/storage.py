from __future__ import annotations

import logging
import mimetypes
import posixpath
import re
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import Settings

logger = logging.getLogger(__name__)

# The artifact formats the inference pipeline actually writes. /media serves
# everything else as application/octet-stream (download, never render):
# artifact names are server-generated UUIDs today, but if a write path ever
# produced an .html artifact, extension-guessing would serve it as text/html
# from the API origin (stored XSS). nginx adds nosniff in the compose path;
# this keeps the direct-exposure and Azure proxy modes equally safe.
_MEDIA_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
}


def _served_media_type(name: str) -> str:
    return _MEDIA_CONTENT_TYPES.get(Path(name).suffix.lower(), "application/octet-stream")


class MediaStorage:
    """Storage facade for annotated media artifacts.

    Local development keeps artifacts on disk. Azure deployments upload the same
    artifacts to Blob Storage while preserving the public `/media/<filename>` API.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def is_azure(self) -> bool:
        return getattr(self.settings, "storage_backend", "local") == "azure_blob"

    def ensure_ready(self) -> None:
        if self.is_azure:
            try:
                self._container_client().create_container()
            except Exception as exc:
                if exc.__class__.__name__ != "ResourceExistsError":
                    raise

    def persist_export(self, local_path: Path) -> str:
        if not self.is_azure:
            return str(local_path)

        blob_name = _safe_export_blob_name(local_path.name)
        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        with local_path.open("rb") as handle:
            self._container_client().upload_blob(
                name=blob_name,
                data=handle,
                overwrite=True,
                content_settings=self._content_settings(content_type),
            )
        local_path.unlink(missing_ok=True)
        return blob_name

    def delete_reference(self, reference: str | None) -> None:
        if not reference:
            return
        if self.is_azure:
            try:
                self._container_client().delete_blob(_normalize_export_blob_name(reference))
            except Exception as exc:  # noqa: BLE001 - best-effort orphan cleanup
                # The DB failure that triggered this cleanup is more important and
                # should not be hidden — but a silently surviving blob is an orphan
                # an operator can only find via this log line.
                logger.warning("Could not delete blob %r during cleanup: %s", reference, exc)
            return
        Path(reference).unlink(missing_ok=True)

    def url_for_reference(self, reference: str | None) -> str | None:
        if not reference:
            return None
        if self.is_azure:
            try:
                blob_name = _normalize_export_blob_name(reference)
            except ValueError:
                # Rows written before the backend switched to azure_blob store the
                # artifact's absolute LOCAL path. The filename is the stable part
                # (server-generated UUID), so map .../exports/<name> onto its blob
                # name instead of dropping the whole History row's media.
                blob_name = _legacy_export_blob_name(reference)
                if blob_name is None:
                    return None
            return f"/media/{blob_name.removeprefix('exports/')}"
        return _local_media_url_for_path(reference, self.settings)

    def response_for_media(self, file_path: str, range_header: str | None = None) -> Response:
        """Serve a media artifact; honors single byte-range requests in BOTH modes.

        Local mode delegates ranges to FileResponse (Starlette implements them).
        Azure mode implements them explicitly: browser <video> seeking — and
        Safari playback at all — require 206 partial responses, which a plain
        StreamingResponse would silently not provide.
        """
        if self.is_azure:
            blob_name = _safe_export_blob_name(file_path)
            media_type = _served_media_type(blob_name)
            client = self._container_client()
            if hasattr(client, "get_blob_client"):
                blob = client.get_blob_client(blob_name)
                get_properties = blob.get_blob_properties
                download_blob = blob.download_blob
            else:
                # Test doubles and older wrappers can expose blob operations on the
                # container object itself. Keep that path while using BlobClient in
                # production, where ContainerClient has no get_blob_properties().
                get_properties = lambda: client.get_blob_properties(blob_name)
                download_blob = lambda **kwargs: client.download_blob(blob_name, **kwargs)
            try:
                size = get_properties().size
                byte_range = _parse_byte_range(range_header, size)
                if byte_range is None:
                    downloader = download_blob()
                    return StreamingResponse(
                        downloader.chunks(),
                        media_type=media_type,
                        headers={"accept-ranges": "bytes", "content-length": str(size)},
                    )
                start, end = byte_range
                downloader = download_blob(offset=start, length=end - start + 1)
                return StreamingResponse(
                    downloader.chunks(),
                    status_code=206,
                    media_type=media_type,
                    headers={
                        "accept-ranges": "bytes",
                        "content-length": str(end - start + 1),
                        "content-range": f"bytes {start}-{end}/{size}",
                    },
                )
            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001 - 404 is the public shape; the cause goes to the log
                # Auth/throttle/network failures must stay diagnosable — a bare
                # 404 with no log line made them indistinguishable from a
                # genuinely missing artifact.
                logger.warning("Blob download failed for %r: %s", blob_name, exc)
                raise HTTPException(status_code=404, detail="Not found") from exc

        target = (self.settings.exports_dir / file_path).resolve()
        # Path-traversal guard. The resolve()d target must live under the
        # exports_dir root; anything else (../../etc/passwd, symlinks pointing
        # outside) gets a 404 — never a 403, so the existence of the gate is
        # not itself an information leak.
        try:
            target.relative_to(self.settings.exports_dir.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not found") from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(target, media_type=_served_media_type(target.name))

    def _container_client(self):
        # MediaStorage instances are created per call, so the (thread-safe,
        # reuse-encouraged) SDK client is cached at module level — without this
        # every /media request and artifact write rebuilt a BlobServiceClient
        # and its connection pool from scratch.
        return _cached_container_client(
            self.settings.azure_storage_connection_string or None,
            self.settings.azure_storage_account_url or None,
            self.settings.blob_container,
        )

    @staticmethod
    def _content_settings(content_type: str):
        from azure.storage.blob import ContentSettings

        return ContentSettings(content_type=content_type)


@lru_cache(maxsize=4)
def _cached_container_client(connection_string: str | None, account_url: str | None, container: str):
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError as exc:
        raise RuntimeError("Install azure-storage-blob to use PAPI_STORAGE_BACKEND=azure_blob.") from exc

    if connection_string:
        service = BlobServiceClient.from_connection_string(connection_string)
    elif account_url:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise RuntimeError("Install azure-identity to use managed identity for Blob Storage.") from exc
        service = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
    else:
        raise RuntimeError(
            "Set AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL "
            "when PAPI_STORAGE_BACKEND=azure_blob."
        )
    return service.get_container_client(container)


def _parse_byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """First satisfiable single byte-range, None for a full-body 200.

    Only the single-range form (``bytes=start-end``, ``bytes=start-``,
    ``bytes=-suffix``) is supported — exactly what browser media elements send.
    Anything unparseable degrades to a full 200 (per RFC 9110 a server MAY
    ignore Range); a parseable-but-unsatisfiable range raises 416 so the
    browser can recover its position.
    """
    if not header or size <= 0:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match:
        return None
    start_raw, end_raw = match.groups()
    if not start_raw and not end_raw:
        return None
    if not start_raw:
        # Suffix form: the last N bytes.
        suffix = int(end_raw)
        if suffix == 0:
            raise HTTPException(
                status_code=416,
                detail="Range not satisfiable",
                headers={"content-range": f"bytes */{size}"},
            )
        start = max(0, size - suffix)
        return start, size - 1
    start = int(start_raw)
    if start >= size:
        raise HTTPException(
            status_code=416,
            detail="Range not satisfiable",
            headers={"content-range": f"bytes */{size}"},
        )
    end = min(int(end_raw), size - 1) if end_raw else size - 1
    if end < start:
        return None
    return start, end


def media_url_for_reference(reference: str | None, settings: Settings) -> str | None:
    return get_media_storage(settings).url_for_reference(reference)


def _local_media_url_for_path(path: str | None, settings: Settings) -> str | None:
    if not path:
        return None
    artifact = Path(path).resolve()
    exports_dir = settings.exports_dir.resolve()
    try:
        relative = artifact.relative_to(exports_dir)
    except ValueError:
        return None
    return f"/media/{relative.as_posix()}"


def _safe_export_blob_name(name: str) -> str:
    return _safe_blob_name("exports", name)


def _safe_blob_name(prefix: str, name: str) -> str:
    normalized = posixpath.normpath(name.replace("\\", "/")).lstrip("/")
    if normalized in ("", ".") or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise HTTPException(status_code=404, detail="Not found")
    if normalized.startswith(f"{prefix}/"):
        return normalized
    return f"{prefix}/{normalized}"


def _legacy_export_blob_name(reference: str) -> str | None:
    """Blob name for a pre-azure_blob DB row (absolute local artifact path), or None.

    Only flat ``.../exports/<name>`` shapes map (local artifacts are written flat);
    anything else — no exports segment, nested remainder, dot segments — stays
    unresolvable rather than guessing.
    """
    normalized = reference.replace("\\", "/")
    marker = "/exports/"
    index = normalized.rfind(marker)
    if index == -1:
        return None
    candidate = normalized[index + len(marker) :]
    if not candidate or "/" in candidate or candidate in (".", ".."):
        return None
    return f"exports/{candidate}"


def _normalize_export_blob_name(reference: str) -> str:
    normalized = posixpath.normpath(reference.replace("\\", "/")).lstrip("/")
    if normalized in ("", ".") or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise ValueError("Invalid blob reference.")
    if not normalized.startswith("exports/"):
        raise ValueError("Blob reference is outside exports.")
    return normalized


def get_media_storage(settings: Settings) -> MediaStorage:
    return MediaStorage(settings)
