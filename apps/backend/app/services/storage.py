from __future__ import annotations

import mimetypes
import posixpath
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import Settings


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

    def persist_upload(self, local_path: Path) -> str:
        if not self.is_azure:
            return str(local_path)

        blob_name = _safe_blob_name("uploads", local_path.name)
        content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
        with local_path.open("rb") as handle:
            self._container_client().upload_blob(
                name=blob_name,
                data=handle,
                overwrite=True,
                content_settings=self._content_settings(content_type),
            )
        # Keep the local file: OpenCV/EXIF readers still need a filesystem path
        # for the current request.
        return blob_name

    def delete_reference(self, reference: str | None) -> None:
        if not reference:
            return
        if self.is_azure:
            try:
                self._container_client().delete_blob(_normalize_export_blob_name(reference))
            except Exception:
                # Best-effort orphan cleanup. The DB failure that triggered this
                # cleanup is more important and should not be hidden.
                return
            return
        Path(reference).unlink(missing_ok=True)

    def url_for_reference(self, reference: str | None) -> str | None:
        if not reference:
            return None
        if self.is_azure:
            try:
                blob_name = _normalize_export_blob_name(reference)
            except ValueError:
                return None
            return f"/media/{blob_name.removeprefix('exports/')}"
        return _local_media_url_for_path(reference, self.settings)

    def response_for_media(self, file_path: str) -> Response:
        if self.is_azure:
            blob_name = _safe_export_blob_name(file_path)
            content_type = mimetypes.guess_type(blob_name)[0] or "application/octet-stream"
            try:
                downloader = self._container_client().download_blob(blob_name)
            except Exception as exc:
                raise HTTPException(status_code=404, detail="Not found") from exc
            return StreamingResponse(downloader.chunks(), media_type=content_type)

        target = (self.settings.exports_dir / file_path).resolve()
        try:
            target.relative_to(self.settings.exports_dir.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not found") from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(target)

    def _container_client(self):
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise RuntimeError("Install azure-storage-blob to use PAPI_STORAGE_BACKEND=azure_blob.") from exc

        if self.settings.azure_storage_connection_string:
            service = BlobServiceClient.from_connection_string(self.settings.azure_storage_connection_string)
        elif self.settings.azure_storage_account_url:
            try:
                from azure.identity import DefaultAzureCredential
            except ImportError as exc:
                raise RuntimeError("Install azure-identity to use managed identity for Blob Storage.") from exc
            service = BlobServiceClient(
                account_url=self.settings.azure_storage_account_url,
                credential=DefaultAzureCredential(),
            )
        else:
            raise RuntimeError(
                "Set AZURE_STORAGE_CONNECTION_STRING or AZURE_STORAGE_ACCOUNT_URL "
                "when PAPI_STORAGE_BACKEND=azure_blob."
            )
        return service.get_container_client(self.settings.blob_container)

    @staticmethod
    def _content_settings(content_type: str):
        from azure.storage.blob import ContentSettings

        return ContentSettings(content_type=content_type)


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


def _normalize_export_blob_name(reference: str) -> str:
    normalized = posixpath.normpath(reference.replace("\\", "/")).lstrip("/")
    if normalized in ("", ".") or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise ValueError("Invalid blob reference.")
    if not normalized.startswith("exports/"):
        raise ValueError("Blob reference is outside exports.")
    return normalized


def get_media_storage(settings: Settings) -> MediaStorage:
    return MediaStorage(settings)
