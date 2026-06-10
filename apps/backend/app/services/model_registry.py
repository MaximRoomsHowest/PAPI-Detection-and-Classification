"""Structured provenance for the serving model.

`/api/model` needs to answer the question an Intersoft safety reviewer actually
asks: *which trained run is serving, and how accurate is it?* The training metrics
live in the run's `results.csv`; `workflows/scripts/populate_model_metrics.py`
distils them into a `model_card.json` placed next to the serving weights. This
module reads that card (provenance + val metrics) and computes the on-disk SHA-256
so the deployed checkpoint can be verified against a release.

If the card is absent (e.g. a local dev checkout with bare weights) every field is
simply ``None`` — the endpoint degrades gracefully rather than failing.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT, Settings

logger = logging.getLogger(__name__)

_HASH_CHUNK_BYTES = 1024 * 1024
_MODEL_CARD_FILENAME = "model_card.json"


@dataclass(frozen=True)
class ModelRegistryEntry:
    id: str
    label: str
    role: str
    path: Path
    class_count: int
    default: bool = False
    description: str | None = None
    card_path: Path | None = None
    card: dict[str, Any] | None = None
    disabled_reason: str | None = None

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def available(self) -> bool:
        return self.exists


@dataclass(frozen=True)
class ModelRegistry:
    default_model_id: str
    entries: tuple[ModelRegistryEntry, ...]

    def get(self, model_id: str | None = None) -> ModelRegistryEntry:
        resolved_id = model_id or self.default_model_id
        for entry in self.entries:
            if entry.id == resolved_id:
                return entry
        raise KeyError(resolved_id)

    def transition_entry(self) -> ModelRegistryEntry | None:
        for entry in self.entries:
            if entry.role == "transition":
                return entry
        return None


@lru_cache(maxsize=8)
def _sha256_cached(path_str: str, mtime_ns: int, size: int) -> str:
    """SHA-256 keyed on (path, mtime, size) so it recomputes only when the file changes."""
    digest = hashlib.sha256()
    with open(path_str, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_sha256(path: Path) -> str | None:
    """Return the SHA-256 hex digest of ``path``, or ``None`` if it cannot be hashed.

    ``None`` is the agreed sentinel for "no digest" (``ModelInfo.sha256`` is optional
    and the only caller passes the result straight through). It covers every reason
    the file is not a readable regular file: absent, a directory, permission-denied,
    or — the race this guards against — deleted/swapped *between* the existence check
    and the read. ``is_file()``, ``stat()`` and the ``open()`` inside ``_sha256_cached``
    are therefore all inside one ``try`` so a TOCTOU disappearance surfaces as the
    sentinel rather than an uncaught ``FileNotFoundError``.
    """
    try:
        if not path.is_file():
            return None
        stat = path.stat()
        return _sha256_cached(str(path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def load_model_card(model_path: Path) -> dict[str, Any] | None:
    """Load the ``model_card.json`` sitting next to the serving weights, or None."""
    card_path = model_path.parent / _MODEL_CARD_FILENAME
    if not card_path.is_file():
        return None
    try:
        data = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_registry_path(raw: str | None, settings: Settings, registry_path: Path) -> Path | None:
    if not raw:
        return None
    expanded = Path(raw).expanduser()
    if expanded.is_absolute():
        return expanded
    parts = expanded.parts
    if parts and parts[0] == "models":
        # Local dev: REPO_ROOT/models/...
        local = REPO_ROOT / expanded
        if local.exists():
            return local.resolve()
        # Docker: /models is bind-mounted while the app lives under /app/apps/backend.
        # parents[1] of PAPI_MODEL_PATH is the models root in both shipped layouts
        # (REPO_ROOT/models/serving/best.pt and /models/serving/best.pt); a checkpoint
        # mounted at a flat custom path breaks this heuristic, so the missing-weights
        # log in load_model_registry names the resolved path for diagnosis.
        model_root = settings.model_path.parents[1] if len(settings.model_path.parents) > 1 else registry_path.parents[1]
        return (model_root / Path(*parts[1:])).resolve()
    if parts and parts[0] == "data":
        return (REPO_ROOT / expanded).resolve()
    return (registry_path.parent / expanded).resolve()


def _legacy_registry(settings: Settings) -> ModelRegistry:
    card = load_model_card(settings.model_path) or {}
    return ModelRegistry(
        default_model_id="default",
        entries=(
            ModelRegistryEntry(
                id="default",
                label=card.get("model_id") or settings.model_path.stem,
                role="detector",
                path=settings.model_path,
                class_count=len(card.get("classes", {}) or {}) or 2,
                default=True,
                card=card,
            ),
        ),
    )


def load_model_registry(settings: Settings) -> ModelRegistry:
    """Load the backend-owned selectable model registry.

    Missing or malformed registry data falls back to the historical single-model
    ``PAPI_MODEL_PATH`` setup so old deployments can still start.
    """
    registry_path = settings.model_registry_path
    data = _read_json(registry_path)
    raw_entries = data.get("models") if data else None
    if not isinstance(raw_entries, list) or not raw_entries:
        return _legacy_registry(settings)

    default_model_id = str(data.get("default_model_id") or "").strip()
    entries: list[ModelRegistryEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            logger.warning("Model registry: skipping entry that is not an object: %r", raw)
            continue
        model_id = str(raw.get("id") or "").strip()
        if not model_id:
            logger.warning("Model registry: skipping entry without an 'id': %r", raw)
            continue
        # One malformed entry (e.g. class_count: "two") must degrade to a skipped
        # entry with a log line — not crash InferenceService.__init__ and thereby
        # 500 every endpoint (audit REG-1). The legacy fallback below still covers
        # the nothing-survived case.
        try:
            role = str(raw.get("role") or "detector").strip().lower()
            path = _resolve_registry_path(str(raw.get("path") or ""), settings, registry_path)
            if path is None:
                logger.warning("Model registry: skipping entry '%s' without a usable 'path'.", model_id)
                continue
            if role == "transition" and settings.transition_model_path is not None:
                path = settings.transition_model_path

            card_path = _resolve_registry_path(str(raw.get("card_path") or ""), settings, registry_path)
            card = _read_json(card_path) if card_path else None
            if card is None:
                card = dict(raw)
            if isinstance(raw.get("val_metrics"), dict):
                card["val_metrics"] = raw["val_metrics"]
            if isinstance(raw.get("classes"), dict):
                card["classes"] = raw["classes"]
            card.setdefault("model_id", model_id)
            card.setdefault("training_run", raw.get("training_run") or model_id)
            card.setdefault("base_weights", raw.get("base_weights"))
            card.setdefault("split_evaluated", raw.get("split_evaluated"))

            entries.append(
                ModelRegistryEntry(
                    id=model_id,
                    label=str(raw.get("label") or model_id),
                    role=role,
                    path=path,
                    class_count=int(raw.get("class_count") or len(card.get("classes", {}) or {}) or 2),
                    default=bool(raw.get("default")),
                    description=str(raw.get("description")) if raw.get("description") else None,
                    card_path=card_path,
                    card=card,
                    disabled_reason=str(raw.get("disabled_reason")) if raw.get("disabled_reason") else None,
                )
            )
        except (ValueError, TypeError) as exc:
            logger.warning("Model registry: skipping malformed entry '%s': %s", model_id, exc)
            continue

    if not entries:
        logger.warning(
            "Model registry at %s yielded no usable entries; falling back to the legacy "
            "single-model setup (PAPI_MODEL_PATH).",
            registry_path,
        )
        return _legacy_registry(settings)
    for entry in entries:
        if not entry.exists:
            # Silent unavailability was undiagnosable (audit PATH-1): name the resolved
            # path once at load so a bad mount/override shows up in the startup log.
            logger.warning(
                "Model registry: weights for '%s' not found at %s; the entry will be "
                "listed as unavailable.",
                entry.id,
                entry.path,
            )
    if not default_model_id or default_model_id not in {entry.id for entry in entries}:
        default_entry = next((entry for entry in entries if entry.default), entries[0])
        default_model_id = default_entry.id
    entries = [replace(entry, default=(entry.id == default_model_id)) for entry in entries]

    # PAPI_MODEL_PATH names the weights the DEFAULT model serves (legacy contract).
    # Apply it to the RESOLVED default — previously it keyed on the raw "default"
    # flag, so flag/default_model_id drift could silently relabel weights or point
    # readiness at a file the actual default never loads (audit DEF-1). When the
    # override changes a declared path, prefer the model card sitting next to the
    # real weights over the registry-inline card, so /api/model never pairs one
    # file's hash with another run's provenance (audit SD-1).
    resolved: list[ModelRegistryEntry] = []
    for entry in entries:
        if entry.id == default_model_id and entry.role != "transition" and entry.path != settings.model_path:
            logger.warning(
                "Model registry: PAPI_MODEL_PATH overrides default model '%s' path %s -> %s.",
                entry.id,
                entry.path,
                settings.model_path,
            )
            entry = replace(
                entry,
                path=settings.model_path,
                card=load_model_card(settings.model_path) or entry.card,
            )
        resolved.append(entry)
    return ModelRegistry(default_model_id=default_model_id, entries=tuple(resolved))
