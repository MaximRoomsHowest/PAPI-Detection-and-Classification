"""Tests for the built-in evaluation-dataset seeding (datasets_seed.py).

Uses a private in-memory SQLite session and a fake eval-seed tree (dummy image
bytes are fine — seeding never decodes the images, it only copies + counts them).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from app.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    from app import models  # noqa: F401 - register all tables

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _make_seed(seed_root: Path, ds_id: str, n: int, class_names: dict[int, str]) -> None:
    folder = seed_root / ds_id
    (folder / "images").mkdir(parents=True, exist_ok=True)
    (folder / "labels").mkdir(parents=True, exist_ok=True)
    classes = sorted(class_names)
    for i in range(n):
        (folder / "images" / f"f{i}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        (folder / "labels" / f"f{i}.txt").write_text(
            f"{classes[i % len(classes)]} 0.5 0.5 0.1 0.1\n", encoding="utf-8"
        )


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(eval_seed_dir=tmp_path / "seed", datasets_dir=tmp_path / "datasets")


def test_seed_builtin_datasets_idempotent(tmp_path, db):
    from app.repositories.datasets import DatasetRepository
    from app.services.datasets_seed import BUILTIN_EVAL_DATASETS, seed_builtin_datasets

    settings = _settings(tmp_path)
    for spec in BUILTIN_EVAL_DATASETS:
        _make_seed(settings.eval_seed_dir, spec["id"], 3, spec["class_names"])

    assert seed_builtin_datasets(settings, db) == len(BUILTIN_EVAL_DATASETS)
    assert seed_builtin_datasets(settings, db) == 0  # second run is a no-op

    repo = DatasetRepository(db)
    for spec in BUILTIN_EVAL_DATASETS:
        row = repo.get(spec["id"])
        assert row is not None
        assert row.source == "builtin"
        assert row.status == "ready"
        assert row.n_test == 3
        root = Path(row.storage_path)
        assert (root / "data.yaml").is_file()
        assert len(list((root / "images" / "test").glob("*.jpg"))) == 3
        assert len(list((root / "labels" / "test").glob("*.txt"))) == 3


def test_seed_skips_missing_source(tmp_path, db):
    from app.services.datasets_seed import seed_builtin_datasets

    settings = _settings(tmp_path)  # no seed tree on disk
    assert seed_builtin_datasets(settings, db) == 0


def test_seed_rebuilds_files_when_volume_wiped(tmp_path, db):
    import shutil

    from app.repositories.datasets import DatasetRepository
    from app.services.datasets_seed import BUILTIN_EVAL_DATASETS, seed_builtin_datasets

    settings = _settings(tmp_path)
    spec = BUILTIN_EVAL_DATASETS[0]
    _make_seed(settings.eval_seed_dir, spec["id"], 2, spec["class_names"])
    assert seed_builtin_datasets(settings, db) == 1

    # Simulate a wiped datasets volume: the row survives, the files are gone.
    root = Path(DatasetRepository(db).get(spec["id"]).storage_path)
    shutil.rmtree(root)
    assert not (root / "data.yaml").exists()

    # Re-seeding rebuilds the on-disk layout (no new row created).
    assert seed_builtin_datasets(settings, db) == 0
    assert (root / "data.yaml").is_file()
    assert len(list((root / "images" / "test").glob("*.jpg"))) == 2


def test_builtin_dataset_cannot_be_deleted(tmp_path, db):
    from app.repositories.datasets import DatasetRepository, ProtectedDatasetError
    from app.services.datasets_seed import BUILTIN_EVAL_DATASETS, seed_builtin_datasets

    settings = _settings(tmp_path)
    spec = BUILTIN_EVAL_DATASETS[0]
    _make_seed(settings.eval_seed_dir, spec["id"], 2, spec["class_names"])
    seed_builtin_datasets(settings, db)

    with pytest.raises(ProtectedDatasetError):
        DatasetRepository(db).delete(spec["id"])
