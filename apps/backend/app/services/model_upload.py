"""Operator model upload + registry insertion.

The keystone of the model-lifecycle feature: the "prepare + run externally"
training launcher ends here too — the operator re-imports the weights they trained
on their own GPU through ``register_model_from_path``.

SECURITY — trust boundary: a ``.pt`` checkpoint is a Python pickle, and loading it
through ``YOLO()`` executes arbitrary code. There is no way to make that safe for
untrusted input through the Ultralytics constructor (``weights_only=True`` is not
reachable). The controls are: (1) the API-key gate on the upload route, (2) the
container hardening already in compose (``cap_drop: ALL``, ``no-new-privileges``),
and (3) preferring ``.onnx`` (no arbitrary-code unpickle) for third-party weights.
Only upload weights you trust.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import Settings
from app.database import get_sessionmaker
from app.models.model_registry import ModelRegistryRow
from app.repositories.model_registry import ModelRegistryRepository
from app.services.model_registry import compute_sha256

logger = logging.getLogger(__name__)

ALLOWED_SUFFIXES = (".pt", ".onnx")
_PEEK_BYTES = 64


def validate_model_signature(upload: UploadFile) -> None:
    """Reject obviously-wrong payloads by magic bytes before any disk write.

    ``.pt`` = a torch ZIP archive (``PK\\x03\\x04``) or a legacy pickle (``\\x80``).
    ``.onnx`` protobuf has no strong magic, so it is accepted on suffix and caught
    by the test-load instead. The stream position is restored either way.
    """
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Only .pt and .onnx model files are supported.")
    try:
        position = upload.file.tell()
        header = upload.file.read(_PEEK_BYTES)
    except (AttributeError, OSError, ValueError) as exc:
        raise ValueError("Could not inspect uploaded model signature.") from exc
    finally:
        try:
            upload.file.seek(position)
        except (NameError, AttributeError, OSError, ValueError):
            pass
    if suffix == ".pt":
        if header.startswith(b"PK\x03\x04") or header[:1] == b"\x80":
            return
        raise ValueError("Uploaded .pt file does not look like a PyTorch checkpoint.")
    # .onnx: accept on suffix; the test-load is the real validator.


def save_model_upload(upload: UploadFile, settings: Settings) -> Path:
    """Stream the weights to the writable user-models dir, enforcing the size cap."""
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Only .pt and .onnx model files are supported.")
    settings.user_models_dir.mkdir(parents=True, exist_ok=True)
    target = settings.user_models_dir / f"{uuid4().hex}{suffix}"
    max_bytes = settings.max_model_upload_mb * 1024 * 1024
    written = 0
    try:
        with target.open("wb") as output:
            while chunk := upload.file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(
                        f"Model upload exceeds the {settings.max_model_upload_mb} MB limit."
                    )
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def test_load_weights(path: Path) -> tuple[int, dict[int, str] | None]:
    """Load the weights through YOLO to catch corrupt/incompatible files and read
    the class names. Raises RuntimeError if the file cannot be loaded.

    NOTE: this is where a malicious ``.pt`` pickle would execute — see the module
    docstring. It runs only after the API-key gate has authorised the upload.
    """
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(f"Unsupported weight type '{suffix}'.")
    os.environ.setdefault("YOLO_AUTOINSTALL", "False")
    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - ultralytics is a hard dep
        raise RuntimeError("Ultralytics is not installed.") from exc
    try:
        model = YOLO(str(path))
    except Exception as exc:  # noqa: BLE001 - any load failure is a bad upload
        raise RuntimeError(f"Weights could not be loaded: {exc}") from exc
    classes: dict[int, str] | None = None
    names = getattr(model, "names", None)
    if isinstance(names, dict):
        try:
            classes = {int(k): str(v) for k, v in names.items()}
        except (TypeError, ValueError):
            classes = None
    class_count = len(classes) if classes else 2
    return class_count, classes


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "model").lower()).strip("-")
    return slug or "model"


def _unique_id(repo: ModelRegistryRepository, base: str) -> str:
    slug = _slugify(base)[:80]
    if repo.get(slug) is None:
        return slug
    for _ in range(50):
        candidate = f"{slug}-{uuid4().hex[:6]}"[:96]
        if repo.get(candidate) is None:
            return candidate
    return f"{slug}-{uuid4().hex}"[:96]


def register_model_from_path(
    settings: Settings,
    path: Path,
    *,
    label: str,
    role: str = "detector",
    description: str | None = None,
    source: str = "uploaded",
    training_run: str | None = None,
    base_weights: str | None = None,
    make_default: bool = False,
    model_id: str | None = None,
) -> ModelRegistryRow:
    """Test-load weights already saved under the user-models dir, insert a registry
    row, and hot-reload the inference service. The caller is responsible for
    unlinking the file if this raises (so a bad upload leaves nothing behind)."""
    class_count, classes = test_load_weights(path)
    sha = compute_sha256(path)
    session = get_sessionmaker()()
    try:
        repo = ModelRegistryRepository(session)
        new_id = _unique_id(repo, model_id or label)
        row = ModelRegistryRow(
            id=new_id,
            label=(label or new_id)[:160],
            role=role,
            source=source,
            storage_path=str(path.resolve()),
            class_count=class_count,
            is_default=False,
            disabled=False,
            protected=False,
            description=description,
            classes_json={str(k): v for k, v in (classes or {}).items()} or None,
            sha256=sha,
            training_run=training_run,
            base_weights=base_weights,
        )
        repo.insert(row)
        if make_default:
            repo.set_default(new_id)
        result_id = row.id
    finally:
        session.close()

    try:
        from app.services.inference import get_inference_service

        get_inference_service().reload_registry()
    except Exception as exc:  # noqa: BLE001 - row is persisted; reload is best-effort
        logger.warning("Registry reload after model import failed: %s", exc)
    logger.info("Registered model '%s' (source=%s, classes=%d).", result_id, source, class_count)
    return row
