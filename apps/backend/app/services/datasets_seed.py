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

from sqlalchemy.orm import Session

from app.config import Settings
from app.models.dataset import Dataset
from app.repositories.datasets import DatasetRepository
from app.services.datasets import (
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

# Each built-in eval set: a fixed id (matches data/eval/<id>/ and the dataset row),
# a display name, and its class map. The 2-class set is auto-used for detector-role
# models, the 3-class set for the transition model (matched by class count).
BUILTIN_EVAL_DATASETS: tuple[dict, ...] = (
    {
        "id": "builtin-detector-redwhite",
        "name": "Built-in · red/white (detector)",
        "class_names": {0: "papi_light_red", 1: "papi_light_white"},
    },
    {
        "id": "builtin-transition-3class",
        "name": "Built-in · red/white/transition",
        "class_names": {0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"},
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
