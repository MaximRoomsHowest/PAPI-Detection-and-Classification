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

from pydantic import ValidationError

from app.config import REPO_ROOT, Settings
from app.validation.schemas import ValMetrics, WeatherMetrics

logger = logging.getLogger(__name__)

_HASH_CHUNK_BYTES = 1024 * 1024
_MODEL_CARD_FILENAME = "model_card.json"

# Card fields that ModelInfo consumes as plain strings. A wrong-typed value
# used to surface only at ModelInfo construction: /api/models dropped the
# whole entry and /api/model leaked the raw pydantic message as a 400.
_CARD_STR_FIELDS = ("model_id", "training_run", "base_weights", "split_evaluated")


def _sanitize_card(card: dict[str, Any], label: str) -> dict[str, Any]:
    """Best-effort hygiene for model-card data at load time (audit B16).

    A malformed optional field degrades to ``None`` with one startup-log
    warning instead of failing later at request time. Notably ``classes``
    must end up dict-or-None: ``len(card.get("classes", {}) or {})`` runs in
    the legacy-registry path OUTSIDE any per-entry isolation, where a
    non-sized value used to 500 every endpoint via InferenceService.__init__.
    """
    for field in _CARD_STR_FIELDS:
        value = card.get(field)
        if value is not None and not isinstance(value, str):
            logger.warning("Model card %s: ignoring non-string '%s'.", label, field)
            card[field] = None
    classes = card.get("classes")
    if classes is not None and not isinstance(classes, dict):
        logger.warning("Model card %s: ignoring non-object 'classes'.", label)
        card["classes"] = None
    val_metrics = card.get("val_metrics")
    if val_metrics is not None:
        try:
            ValMetrics.model_validate(val_metrics)
        except ValidationError:
            logger.warning("Model card %s: ignoring malformed 'val_metrics'.", label)
            card["val_metrics"] = None
    weather_metrics = card.get("weather_metrics")
    if weather_metrics is not None:
        try:
            WeatherMetrics.model_validate(weather_metrics)
        except ValidationError:
            logger.warning("Model card %s: ignoring malformed 'weather_metrics'.", label)
            card["weather_metrics"] = None
    return card


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
    # Operator-disabled (DB-backed registry): the entry stays listed (greyed out)
    # but is never auto-selected or preloaded. Defaults False so every existing
    # construction site (legacy/JSON loaders) keeps ``available == exists``.
    disabled: bool = False
    # Provenance + delete-protection, surfaced to the management UI. Defaults keep
    # the JSON/legacy loaders (which build "builtin", non-protected entries) intact.
    source: str = "builtin"
    protected: bool = False

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def available(self) -> bool:
        # A disabled entry is unavailable for inference even when its weights exist,
        # so explicit selection is rejected and preload skips it.
        return self.exists and not self.disabled


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
    if not isinstance(data, dict):
        return None
    return _sanitize_card(data, str(card_path))


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
            if isinstance(raw.get("weather_metrics"), dict):
                card["weather_metrics"] = raw["weather_metrics"]
            if isinstance(raw.get("classes"), dict):
                card["classes"] = raw["classes"]
            card.setdefault("model_id", model_id)
            card.setdefault("training_run", raw.get("training_run") or model_id)
            card.setdefault("base_weights", raw.get("base_weights"))
            card.setdefault("split_evaluated", raw.get("split_evaluated"))
            # Sanitize AFTER the merge/setdefault block so wrong-typed values
            # smuggled in from either the card file or the inline registry
            # entry are caught in one place.
            card = _sanitize_card(card, model_id)

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


def _frozen_weather_metrics(settings: Settings) -> dict[str, dict[str, Any]]:
    """Map model_id -> weather_metrics from the frozen ``models.json``.

    Per-condition weather robustness is STATIC reference data tied to the committed
    registry — unlike ``val_metrics``, which the evaluate job writes back per-row to the
    mutable DB and which is therefore deliberately NOT reconciled from JSON. Sourcing
    weather metrics from the JSON keeps them in sync with ``models.json`` edits without a
    DB column or migration, so the DB-backed registry surfaces them unchanged. Empty on
    any read failure (no models.json in the single-model/dev path).
    """
    data = _read_json(settings.model_registry_path)
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw in data.get("models", []):
        if isinstance(raw, dict) and isinstance(raw.get("weather_metrics"), dict):
            out[str(raw.get("id"))] = raw["weather_metrics"]
    return out


def registry_from_rows(rows: list[Any], settings: Settings) -> ModelRegistry:
    """Build the in-memory frozen registry from ``model_registry`` table rows.

    This is the mutable-registry counterpart to ``load_model_registry`` (which reads
    the read-only JSON). Built-in rows store repo-relative paths resolved via
    ``_resolve_registry_path``; uploaded/trained rows store absolute paths that the
    same resolver passes through unchanged. A row's provenance/metrics are packed
    into the entry ``card`` so ``_model_info_for_entry`` surfaces them unchanged.
    """
    entries: list[ModelRegistryEntry] = []
    default_id = ""
    # Static per-model weather robustness lives in the frozen JSON, not the mutable DB.
    frozen_weather = _frozen_weather_metrics(settings)
    for row in rows:
        path = _resolve_registry_path(str(row.storage_path or ""), settings, settings.model_registry_path)
        if path is None:
            path = Path(str(row.storage_path or ""))
        # The transition slot still honours PAPI_TRANSITION_MODEL_PATH so the compose
        # mechanism for enabling the optional 3-class model keeps working.
        if row.role == "transition" and settings.transition_model_path is not None:
            path = settings.transition_model_path
        card: dict[str, Any] = {
            "model_id": row.id,
            "training_run": row.training_run or row.id,
            "base_weights": row.base_weights,
            "split_evaluated": row.split_evaluated,
        }
        if isinstance(row.classes_json, dict):
            card["classes"] = row.classes_json
        if isinstance(row.val_metrics_json, dict):
            card["val_metrics"] = row.val_metrics_json
        weather = frozen_weather.get(str(row.id))
        if isinstance(weather, dict):
            card["weather_metrics"] = weather
        card = _sanitize_card(card, str(row.id))
        entries.append(
            ModelRegistryEntry(
                id=str(row.id),
                label=str(row.label or row.id),
                role=str(row.role or "detector"),
                path=path,
                class_count=int(row.class_count or 2),
                default=bool(row.is_default),
                description=row.description,
                card=card,
                disabled=bool(row.disabled),
                disabled_reason=row.disabled_reason,
                source=str(row.source or "builtin"),
                protected=bool(row.protected),
            )
        )
        if row.is_default:
            default_id = str(row.id)
    if not entries:
        # No rows yet — fall back to the frozen JSON/legacy loader so the service
        # still serves while the table is being seeded.
        return load_model_registry(settings)
    if not default_id or default_id not in {entry.id for entry in entries}:
        default_id = entries[0].id
        entries = [replace(entry, default=(entry.id == default_id)) for entry in entries]
    return ModelRegistry(default_model_id=default_id, entries=tuple(entries))


def resolve_weights_path(settings: Settings, model_id: str) -> Path:
    """Resolve a registry id to its on-disk weights path (for background jobs).

    Jobs load their OWN ``YOLO`` instance from this path — they never touch the
    inference service's cache or lock. Raises ``KeyError`` for an unknown id and
    ``FileNotFoundError`` when the weights are missing.
    """
    registry = build_registry_from_db(settings)
    try:
        entry = registry.get(model_id)
    except KeyError as exc:
        raise KeyError(f"Unknown model_id: {model_id}") from exc
    if not entry.path.is_file():
        raise FileNotFoundError(f"Weights for model '{model_id}' not found at {entry.path}.")
    return entry.path


def _can_use_process_registry_db(settings: Settings) -> bool:
    """Return true when ``settings`` belongs to the process-global app context.

    The database engine/sessionmaker are also process-global and are built from
    ``get_settings()``. Direct ``Settings(...)`` instances are used heavily by
    unit tests and tooling to point at temporary model registries; letting those
    objects query the global database cross-contaminates otherwise isolated
    registry fixtures with the developer's local model rows.
    """
    try:
        from app.config import get_settings
    except Exception:  # noqa: BLE001 - keep registry loading resilient at startup
        return False
    return settings is get_settings()


def build_registry_from_db(settings: Settings) -> ModelRegistry:
    """Load the registry from the database, falling back to the frozen JSON loader.

    The fallback keeps the no-DB dev path and the very first boot (before seeding)
    alive: an unreachable DB or an empty table both yield the legacy single-model
    or JSON registry rather than an empty selector.
    """
    if not _can_use_process_registry_db(settings):
        return load_model_registry(settings)
    try:
        from app.database import get_sessionmaker
        from app.repositories.model_registry import ModelRegistryRepository

        session = get_sessionmaker()()
    except Exception:  # noqa: BLE001 - any DB wiring failure degrades to the JSON loader
        return load_model_registry(settings)
    try:
        rows = ModelRegistryRepository(session).list_all()
    except Exception:  # noqa: BLE001 - table missing / query error degrades to JSON
        return load_model_registry(settings)
    finally:
        session.close()
    if not rows:
        return load_model_registry(settings)
    return registry_from_rows(rows, settings)
