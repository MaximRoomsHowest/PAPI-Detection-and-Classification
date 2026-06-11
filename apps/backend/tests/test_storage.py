"""MediaStorage facade: identical serving rules for local and Azure backends.

The Azure SDK is never imported here — the container client is monkeypatched —
so the suite runs in environments without azure-storage-blob installed (the
import inside ``_container_client`` is lazy by design).
"""

import pytest
from app.config import Settings
from app.services.storage import (
    MediaStorage,
    _legacy_export_blob_name,
    _normalize_export_blob_name,
    _safe_blob_name,
    _served_media_type,
    get_media_storage,
    media_url_for_reference,
)
from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse


def local_settings(tmp_path) -> Settings:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
    )
    settings.ensure_storage()
    return settings


def azure_settings(tmp_path) -> Settings:
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=tmp_path / "models" / "best.pt",
        storage_backend="azure_blob",
    )
    settings.ensure_storage()
    return settings


class FakeDownloader:
    def chunks(self):
        return iter([b"data"])


class FakeContainerClient:
    """Records calls; raises whatever exception instances it was armed with."""

    def __init__(self, download_error=None, delete_error=None, create_error=None):
        self.download_error = download_error
        self.delete_error = delete_error
        self.create_error = create_error
        self.uploads: list[tuple[str, bytes]] = []
        self.deleted: list[str] = []
        self.created = 0

    def upload_blob(self, name, data, overwrite, content_settings):  # noqa: ARG002
        self.uploads.append((name, data.read()))

    def download_blob(self, blob_name):  # noqa: ARG002
        if self.download_error is not None:
            raise self.download_error
        return FakeDownloader()

    def delete_blob(self, blob_name):
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append(blob_name)

    def create_container(self):
        self.created += 1
        if self.create_error is not None:
            raise self.create_error


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeContainerClient()
    monkeypatch.setattr(MediaStorage, "_container_client", lambda self: client)
    # ContentSettings lives in the azure SDK; the upload path only forwards it.
    monkeypatch.setattr(MediaStorage, "_content_settings", staticmethod(lambda content_type: content_type))
    return client


# --- blob-name sanitisation -------------------------------------------------


def test_safe_blob_name_prefixes_and_normalises():
    assert _safe_blob_name("exports", "frame.jpg") == "exports/frame.jpg"
    assert _safe_blob_name("exports", "exports/frame.jpg") == "exports/frame.jpg"
    assert _safe_blob_name("uploads", "a\\b.jpg") == "uploads/a/b.jpg"


@pytest.mark.parametrize("name", ["", ".", "../secret", "a/../../secret"])
def test_safe_blob_name_rejects_traversal(name):
    with pytest.raises(HTTPException) as excinfo:
        _safe_blob_name("exports", name)
    assert excinfo.value.status_code == 404


def test_normalize_export_blob_name_requires_exports_prefix():
    assert _normalize_export_blob_name("exports/frame.jpg") == "exports/frame.jpg"
    with pytest.raises(ValueError):
        _normalize_export_blob_name("uploads/frame.jpg")
    with pytest.raises(ValueError):
        _normalize_export_blob_name("../exports/frame.jpg")


def test_legacy_export_blob_name_maps_flat_local_paths_only():
    assert _legacy_export_blob_name("/app/storage/exports/uuid_annotated.jpg") == "exports/uuid_annotated.jpg"
    assert _legacy_export_blob_name("C:\\storage\\exports\\clip.webm") == "exports/clip.webm"
    assert _legacy_export_blob_name("/app/storage/uploads/raw.jpg") is None
    assert _legacy_export_blob_name("/app/storage/exports/nested/x.jpg") is None
    assert _legacy_export_blob_name("/app/storage/exports/") is None


# --- content-type allowlist -------------------------------------------------


def test_served_media_type_allowlists_artifact_formats():
    assert _served_media_type("frame.JPG") == "image/jpeg"
    assert _served_media_type("clip.mp4") == "video/mp4"
    # Anything the pipeline does not write downloads instead of rendering
    # (stored-XSS guard: .html must never be served as text/html).
    assert _served_media_type("page.html") == "application/octet-stream"
    assert _served_media_type("noext") == "application/octet-stream"


# --- local serving ----------------------------------------------------------


def test_response_for_media_local_serves_with_allowlisted_type(tmp_path):
    settings = local_settings(tmp_path)
    (settings.exports_dir / "frame.jpg").write_bytes(b"jpeg")

    response = get_media_storage(settings).response_for_media("frame.jpg")

    assert isinstance(response, FileResponse)
    assert response.media_type == "image/jpeg"


def test_response_for_media_local_unknown_suffix_downloads(tmp_path):
    settings = local_settings(tmp_path)
    (settings.exports_dir / "page.html").write_bytes(b"<script>")

    response = get_media_storage(settings).response_for_media("page.html")

    assert response.media_type == "application/octet-stream"


@pytest.mark.parametrize("path", ["../uploads/raw.jpg", "missing.jpg"])
def test_response_for_media_local_rejects_traversal_and_missing(tmp_path, path):
    settings = local_settings(tmp_path)
    (settings.uploads_dir / "raw.jpg").write_bytes(b"x")

    with pytest.raises(HTTPException) as excinfo:
        get_media_storage(settings).response_for_media(path)
    assert excinfo.value.status_code == 404


# --- azure serving ----------------------------------------------------------


def test_response_for_media_azure_streams_with_allowlisted_type(tmp_path, fake_client):
    settings = azure_settings(tmp_path)

    response = get_media_storage(settings).response_for_media("clip.mp4")

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "video/mp4"


def test_response_for_media_azure_download_failure_is_404(tmp_path, monkeypatch):
    client = FakeContainerClient(download_error=RuntimeError("blob gone"))
    monkeypatch.setattr(MediaStorage, "_container_client", lambda self: client)
    settings = azure_settings(tmp_path)

    with pytest.raises(HTTPException) as excinfo:
        get_media_storage(settings).response_for_media("clip.mp4")
    assert excinfo.value.status_code == 404


# --- url_for_reference ------------------------------------------------------


def test_url_for_reference_local_requires_exports_tree(tmp_path):
    settings = local_settings(tmp_path)
    inside = settings.exports_dir / "frame.jpg"

    storage = get_media_storage(settings)
    assert storage.url_for_reference(str(inside)) == "/media/frame.jpg"
    assert storage.url_for_reference(str(settings.uploads_dir / "raw.jpg")) is None
    assert storage.url_for_reference(None) is None


def test_url_for_reference_azure_blob_and_legacy_rows(tmp_path):
    storage = get_media_storage(azure_settings(tmp_path))

    assert storage.url_for_reference("exports/frame.jpg") == "/media/frame.jpg"
    # Pre-switch DB rows hold absolute local paths; the filename still resolves.
    assert storage.url_for_reference("/app/storage/exports/frame.jpg") == "/media/frame.jpg"
    assert storage.url_for_reference("not-an-export") is None


def test_media_url_for_reference_helper_matches_backend(tmp_path):
    settings = azure_settings(tmp_path)
    assert media_url_for_reference("exports/frame.jpg", settings) == "/media/frame.jpg"


# --- persistence ------------------------------------------------------------


def test_persist_export_local_keeps_file_and_returns_path(tmp_path):
    settings = local_settings(tmp_path)
    artifact = settings.exports_dir / "frame.jpg"
    artifact.write_bytes(b"jpeg")

    reference = get_media_storage(settings).persist_export(artifact)

    assert reference == str(artifact)
    assert artifact.exists()


def test_persist_export_azure_uploads_and_removes_local_copy(tmp_path, fake_client):
    settings = azure_settings(tmp_path)
    artifact = settings.exports_dir / "frame.jpg"
    artifact.write_bytes(b"jpeg")

    reference = get_media_storage(settings).persist_export(artifact)

    assert reference == "exports/frame.jpg"
    assert fake_client.uploads == [("exports/frame.jpg", b"jpeg")]
    assert not artifact.exists()


def test_persist_upload_azure_keeps_local_copy_for_inference(tmp_path, fake_client):
    settings = azure_settings(tmp_path)
    upload = settings.uploads_dir / "raw.jpg"
    upload.write_bytes(b"jpeg")

    reference = get_media_storage(settings).persist_upload(upload)

    assert reference == "uploads/raw.jpg"
    assert fake_client.uploads == [("uploads/raw.jpg", b"jpeg")]
    # OpenCV/EXIF readers still need the filesystem path for the current request.
    assert upload.exists()


# --- delete_reference -------------------------------------------------------


def test_delete_reference_local_unlinks(tmp_path):
    settings = local_settings(tmp_path)
    artifact = settings.exports_dir / "frame.jpg"
    artifact.write_bytes(b"jpeg")

    get_media_storage(settings).delete_reference(str(artifact))

    assert not artifact.exists()


def test_delete_reference_azure_failure_is_logged_not_raised(tmp_path, monkeypatch, caplog):
    client = FakeContainerClient(delete_error=RuntimeError("throttled"))
    monkeypatch.setattr(MediaStorage, "_container_client", lambda self: client)
    settings = azure_settings(tmp_path)

    with caplog.at_level("WARNING", logger="app.services.storage"):
        get_media_storage(settings).delete_reference("exports/frame.jpg")

    assert any("Could not delete blob" in record.message for record in caplog.records)


def test_delete_reference_azure_deletes_blob(tmp_path, fake_client):
    settings = azure_settings(tmp_path)

    get_media_storage(settings).delete_reference("exports/frame.jpg")

    assert fake_client.deleted == ["exports/frame.jpg"]


# --- ensure_ready -----------------------------------------------------------


def test_ensure_ready_tolerates_existing_container(tmp_path, monkeypatch):
    class ResourceExistsError(Exception):
        pass

    client = FakeContainerClient(create_error=ResourceExistsError("exists"))
    monkeypatch.setattr(MediaStorage, "_container_client", lambda self: client)

    get_media_storage(azure_settings(tmp_path)).ensure_ready()

    assert client.created == 1


def test_ensure_ready_raises_on_real_failures(tmp_path, monkeypatch):
    client = FakeContainerClient(create_error=RuntimeError("auth failed"))
    monkeypatch.setattr(MediaStorage, "_container_client", lambda self: client)

    with pytest.raises(RuntimeError, match="auth failed"):
        get_media_storage(azure_settings(tmp_path)).ensure_ready()


def test_ensure_ready_local_is_noop(tmp_path):
    # Must not require the azure SDK or any client at all.
    get_media_storage(local_settings(tmp_path)).ensure_ready()
