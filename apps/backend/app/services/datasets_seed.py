"""Seed the built-in, per-role evaluation datasets on startup.

The app ships a small, committed evaluation set per model role so the Models page
can evaluate any model out of the box (no upload required):

* ``builtin-detector-redwhite`` — 2-class (red/white), for detector-role models.
* ``builtin-transition-3class`` — 3-class (red/white/transition), for the transition model.

The committed seeds live under ``settings.eval_seed_dir`` (the repo's ``data/eval``,
or a read-only mount in Docker). Each is copied into the datasets volume as a
``test``-split YOLO dataset (the exact layout ``evaluate.py`` consumes) and registered
as a ``source="builtin"`` :class:`Dataset` row with a fixed id. Idempotent per id, and
it rebuilds the on-disk layout if the datasets volume was wiped while the row survived.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.dataset import Dataset
from app.repositories.datasets import DatasetRepository
from app.services.datasets import (
    DEFAULT_CLASS_NAMES,
    IMAGE_SUFFIXES,
    dataset_root,
    ensure_dataset_dirs,
    refresh_counts,
    write_data_yaml,
    write_split_files,
)

logger = logging.getLogger(__name__)

# Marks a dataset as a protected, app-shipped evaluation set (undeletable, badged).
BUILTIN_SOURCE = "builtin"

# Marks a full on-disk project dataset (real training/eval data) registered in place.
PROJECT_SOURCE = "project"

# The project datasets to register on the Datasets page, by id + path under
# settings.project_datasets_dir (data/datasets). Each is registered IN PLACE — the
# row points at the existing directory; nothing is copied. Class names and split
# counts are read from the dataset's own data.yaml so both the standard images/<split>
# layout (2-class detector) and the txt-list-split layout (3-class transition, which
# ultralytics reads natively) are handled.
PROJECT_DATASETS: tuple[dict, ...] = (
    {
        "id": "project-2class-detector",
        "subpath": "papi-2class-detection-flightsplit",
        "name": "Project · 2-class detector (flight-split)",
    },
    {
        "id": "project-transition-3class",
        "subpath": "transition-classification-data/transition_combined",
        "name": "Project · 3-class transition",
    },
)

# Each built-in eval set: a fixed id (matches data/eval/<id>/ and the dataset row),
# a display name, and its class map. The 2-class set is auto-used for detector-role
# models, the 3-class set for the transition model (matched by class count).
BUILTIN_EVAL_DATASETS: tuple[dict, ...] = (
    {
        "id": "builtin-detector-redwhite",
        "name": "Built-in · red/white (detector)",
        # Derived from the canonical DEFAULT_CLASS_NAMES so the seed can never drift from
        # the trainer/evaluator's class map (single source of truth).
        "class_names": {k: DEFAULT_CLASS_NAMES[k] for k in (0, 1)},
    },
    {
        "id": "builtin-transition-3class",
        "name": "Built-in · red/white/transition",
        "class_names": dict(DEFAULT_CLASS_NAMES),
    },
)


def _populate_test_split(seed_src: Path, root: Path, class_names: dict[int, str]) -> tuple[int, int, int]:
    """Copy the committed seed images/labels into ``root`` as the ``test`` split and
    (re)write the split files + data.yaml. Returns (n_train, n_val, n_test)."""
    ensure_dataset_dirs(root)
    img_dst = root / "images" / "test"
    lab_dst = root / "labels" / "test"
    # Clear the test split first so a re-seed onto a stale volume is clean.
    for folder in (img_dst, lab_dst):
        for stale in folder.glob("*"):
            if stale.is_file():
                stale.unlink()
    for img in sorted((seed_src / "images").iterdir()):
        if img.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        shutil.copyfile(img, img_dst / img.name)
        label = seed_src / "labels" / f"{img.stem}.txt"
        if label.is_file():
            shutil.copyfile(label, lab_dst / label.name)
    write_split_files(root)
    write_data_yaml(root, class_names)
    return refresh_counts(root)


def seed_builtin_datasets(settings: Settings, session: Session) -> int:
    """Idempotently seed every built-in eval dataset. Returns the count newly created.

    Per id: skip when the row exists AND its on-disk data.yaml + test images are
    present; otherwise (re)build the files and upsert the row. Missing seed sources
    (e.g. the mount is absent) are logged and skipped — never fatal.
    """
    seed_root = Path(settings.eval_seed_dir)
    repo = DatasetRepository(session)
    seeded = 0
    for spec in BUILTIN_EVAL_DATASETS:
        seed_src = seed_root / spec["id"]
        if not (seed_src / "images").is_dir():
            logger.info("Built-in eval seed '%s' not found at %s; skipping.", spec["id"], seed_src)
            continue
        root = dataset_root(settings, spec["id"])
        data_yaml = root / "data.yaml"
        existing = repo.get(spec["id"])
        if existing is not None and data_yaml.is_file() and existing.n_test > 0:
            continue  # already seeded and the files are still on the volume

        n_train, n_val, n_test = _populate_test_split(seed_src, root, spec["class_names"])
        class_names_json = {str(k): v for k, v in spec["class_names"].items()}
        if existing is None:
            # Fixed id (not the uuid default) so the set is stable + role-matchable.
            session.add(
                Dataset(
                    id=spec["id"],
                    name=spec["name"][:160],
                    source=BUILTIN_SOURCE,
                    status="ready",
                    storage_path=str(root),
                    class_names_json=class_names_json,
                    n_train=n_train,
                    n_val=n_val,
                    n_test=n_test,
                    data_yaml_path=str(data_yaml),
                )
            )
            session.commit()
            seeded += 1
        else:
            existing.source = BUILTIN_SOURCE
            existing.status = "ready"
            existing.storage_path = str(root)
            existing.class_names_json = class_names_json
            existing.n_train, existing.n_val, existing.n_test = n_train, n_val, n_test
            existing.data_yaml_path = str(data_yaml)
            session.commit()
    return seeded


def _read_data_yaml(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _class_names_from_yaml(meta: dict) -> dict[int, str]:
    """Parse YOLO ``names`` (dict {0: 'red', ...} or list ['red', ...]) → {int: str}."""
    names = meta.get("names")
    if isinstance(names, dict):
        out: dict[int, str] = {}
        for key, value in names.items():
            try:
                out[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(names, list):
        return {i: str(value) for i, value in enumerate(names)}
    return {}


def _count_split(root: Path, value) -> int:
    """Count one split, resolved relative to the dataset root. Handles both a split
    DIRECTORY (``images/train`` → count image files) and a LIST FILE (``train.txt`` →
    count non-empty lines), so the txt-list datasets ultralytics reads still show real
    counts on the card. Empty/missing → 0."""
    if not isinstance(value, str) or not value.strip():
        return 0
    target = root / value
    try:
        if target.is_dir():
            return sum(
                1 for p in target.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
            )
        if target.is_file() and target.suffix.lower() == ".txt":
            return sum(1 for line in target.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0
    return 0


def seed_project_datasets(settings: Settings, session: Session) -> int:
    """Register the full on-disk project datasets IN PLACE (no copy). Returns the count
    newly registered.

    Each :data:`PROJECT_DATASETS` entry whose ``data.yaml`` is present under
    ``settings.project_datasets_dir`` is upserted as a ``source="project"`` row pointing
    straight at that directory, with class names + split counts read from its own
    data.yaml. Idempotent per id; absent datasets (fresh clone / Docker image without the
    gitignored data) are logged and skipped — never fatal.
    """
    base = Path(settings.project_datasets_dir)
    repo = DatasetRepository(session)
    seeded = 0
    for spec in PROJECT_DATASETS:
        root = (base / spec["subpath"]).resolve()
        data_yaml = root / "data.yaml"
        if not data_yaml.is_file():
            logger.info("Project dataset '%s' not found at %s; skipping.", spec["id"], data_yaml)
            continue
        existing = repo.get(spec["id"])
        if existing is not None and existing.source == PROJECT_SOURCE:
            continue  # already registered

        meta = _read_data_yaml(data_yaml)
        class_names_json = {str(k): v for k, v in _class_names_from_yaml(meta).items()} or None
        n_train = _count_split(root, meta.get("train"))
        n_val = _count_split(root, meta.get("val"))
        n_test = _count_split(root, meta.get("test"))
        if existing is None:
            session.add(
                Dataset(
                    id=spec["id"],
                    name=spec["name"][:160],
                    source=PROJECT_SOURCE,
                    status="ready",
                    storage_path=str(root),
                    class_names_json=class_names_json,
                    n_train=n_train,
                    n_val=n_val,
                    n_test=n_test,
                    data_yaml_path=str(data_yaml),
                )
            )
        else:
            existing.source = PROJECT_SOURCE
            existing.status = "ready"
            existing.storage_path = str(root)
            existing.class_names_json = class_names_json
            existing.n_train, existing.n_val, existing.n_test = n_train, n_val, n_test
            existing.data_yaml_path = str(data_yaml)
        session.commit()
        seeded += 1
    return seeded
