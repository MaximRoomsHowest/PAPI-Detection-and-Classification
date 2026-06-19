"""Tests for the model-lifecycle feature set (upload / evaluate / datasets / train).

Repo + service logic is tested against a private in-memory SQLite engine (no global
caches); the HTTP layer is tested with a shared in-memory DB, a fake job runner
(so no real YOLO/threads run), and a mocked weight test-load.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# --------------------------------------------------------------------------- #
# Private-DB fixture for repo/service unit tests                              #
# --------------------------------------------------------------------------- #
@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    from app import models  # noqa: F401 - register all tables

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


def _frozen_registry():
    """A minimal frozen registry to seed from (default + a transition entry)."""
    from app.services.model_registry import ModelRegistry, ModelRegistryEntry

    return ModelRegistry(
        default_model_id="small",
        entries=(
            ModelRegistryEntry(
                id="small",
                label="Small detector",
                role="detector",
                path=Path("models/serving/best.pt"),
                class_count=2,
                default=True,
                card={"classes": {"0": "PAPI-Red", "1": "PAPI-White"}},
            ),
            ModelRegistryEntry(
                id="transition",
                label="Transition",
                role="transition",
                path=Path("data/runs/x/best.pt"),
                class_count=3,
                card={"val_metrics": {"map50": 0.6}},
            ),
        ),
    )


# --------------------------------------------------------------------------- #
# ModelRegistryRepository                                                      #
# --------------------------------------------------------------------------- #
def test_seed_is_idempotent_and_protects_serving_model(db):
    from app.repositories.model_registry import ModelRegistryRepository

    repo = ModelRegistryRepository(db)
    assert repo.seed_from_frozen(_frozen_registry()) == 2
    # Second call is a no-op (table already seeded).
    assert repo.seed_from_frozen(_frozen_registry()) == 0
    small = repo.get("small")
    assert small.is_default is True
    assert small.protected is True  # committed serving model
    assert repo.get("transition").protected is False


def test_reconcile_repairs_stale_builtin_paths_without_clobbering_operator_state(db):
    from app.models.model_registry import ModelRegistryRow
    from app.repositories.model_registry import ModelRegistryRepository

    repo = ModelRegistryRepository(db)
    repo.seed_from_frozen(_frozen_registry())
    small = repo.get("small")
    small.storage_path = "best.pt"
    small.label = "Old small"
    small.disabled = True
    small.disabled_reason = "Operator disabled for comparison."
    db.commit()
    repo.insert(
        ModelRegistryRow(
            id="uploaded",
            label="Up",
            role="detector",
            source="uploaded",
            storage_path="/abs/up.pt",
            class_count=2,
        )
    )
    repo.set_default("uploaded")

    assert repo.reconcile_builtins_from_frozen(_frozen_registry()) == 1
    assert Path(repo.get("small").storage_path) == Path("models/serving/best.pt")
    assert repo.get("small").label == "Small detector"
    assert repo.get("small").disabled is True
    assert repo.get("small").disabled_reason == "Operator disabled for comparison."
    assert repo.get("uploaded").is_default is True
    assert repo.get("uploaded").storage_path == "/abs/up.pt"


def test_reconcile_preserves_operator_evaluation_metrics(db):
    """Regression (found in live user testing): an in-app Evaluate of a BUILT-IN model
    writes val_metrics; a restart's reconcile must NOT revert them to the frozen
    models.json — re-evaluating a built-in has to survive a restart."""
    from app.repositories.model_registry import ModelRegistryRepository

    repo = ModelRegistryRepository(db)
    repo.seed_from_frozen(_frozen_registry())
    # 'transition' seeds with frozen val_metrics (map50=0.6); operator re-evaluates it.
    repo.update_val_metrics("transition", {"map50": 0.99, "precision": 0.9}, split="test")
    # 'small' seeds without val_metrics; operator evaluates it for the first time.
    repo.update_val_metrics("small", {"map50": 0.95}, split="test")

    repo.reconcile_builtins_from_frozen(_frozen_registry())

    assert repo.get("transition").val_metrics_json["map50"] == 0.99  # NOT reverted to 0.6
    assert repo.get("transition").split_evaluated == "test"
    assert repo.get("small").val_metrics_json["map50"] == 0.95
    # Provenance/path repair still happens (storage_path stays the resolved frozen path).
    assert Path(repo.get("small").storage_path) == Path("models/serving/best.pt")


def test_promote_swaps_default(db):
    from app.models.model_registry import ModelRegistryRow
    from app.repositories.model_registry import ModelRegistryRepository

    repo = ModelRegistryRepository(db)
    repo.seed_from_frozen(_frozen_registry())
    repo.insert(
        ModelRegistryRow(id="uploaded", label="Up", role="detector", source="uploaded",
                         storage_path="/abs/up.pt", class_count=2)
    )
    repo.set_default("uploaded")
    assert repo.get("uploaded").is_default is True
    assert repo.get("small").is_default is False


def test_delete_protected_and_default_are_refused(db):
    from app.repositories.model_registry import (
        DefaultModelError,
        ModelRegistryRepository,
        ProtectedModelError,
    )

    repo = ModelRegistryRepository(db)
    repo.seed_from_frozen(_frozen_registry())
    # 'small' is both protected AND default -> protected check wins.
    with pytest.raises(ProtectedModelError):
        repo.delete("small")
    # A non-protected default cannot be deleted either.
    from app.models.model_registry import ModelRegistryRow

    repo.insert(
        ModelRegistryRow(id="up", label="Up", role="detector", source="uploaded",
                         storage_path="/abs/up.pt", class_count=2)
    )
    repo.set_default("up")  # up is now default (not protected)
    with pytest.raises(DefaultModelError):
        repo.delete("up")


def test_disable_refuses_default_then_disables_other(db):
    from app.models.model_registry import ModelRegistryRow
    from app.repositories.model_registry import DefaultModelError, ModelRegistryRepository

    repo = ModelRegistryRepository(db)
    repo.seed_from_frozen(_frozen_registry())
    with pytest.raises(DefaultModelError):
        repo.disable("small")  # default
    repo.insert(
        ModelRegistryRow(id="up", label="Up", role="detector", source="uploaded",
                         storage_path="/abs/up.pt", class_count=2)
    )
    repo.disable("up", "manual")
    assert repo.get("up").disabled is True


def test_update_val_metrics(db):
    from app.models.model_registry import ModelRegistryRow
    from app.repositories.model_registry import ModelRegistryRepository

    repo = ModelRegistryRepository(db)
    repo.insert(
        ModelRegistryRow(id="up", label="Up", role="detector", source="uploaded",
                         storage_path="/abs/up.pt", class_count=2)
    )
    repo.update_val_metrics("up", {"map50": 0.9, "per_class": {"red": {"f1": 0.8}}}, split="test")
    row = repo.get("up")
    assert row.val_metrics_json["map50"] == 0.9
    assert row.split_evaluated == "test"


# --------------------------------------------------------------------------- #
# registry_from_rows bridge                                                    #
# --------------------------------------------------------------------------- #
def test_registry_from_rows_maps_default_and_disabled(db):
    from app.config import Settings
    from app.models.model_registry import ModelRegistryRow
    from app.repositories.model_registry import ModelRegistryRepository
    from app.services.model_registry import registry_from_rows

    repo = ModelRegistryRepository(db)
    repo.seed_from_frozen(_frozen_registry())
    repo.insert(
        ModelRegistryRow(id="up", label="Up", role="detector", source="uploaded",
                         storage_path="/abs/up.pt", class_count=2, disabled=True,
                         disabled_reason="hidden")
    )
    registry = registry_from_rows(repo.list_all(), Settings())
    assert registry.default_model_id == "small"
    up = next(e for e in registry.entries if e.id == "up")
    assert up.disabled is True
    assert up.available is False  # disabled => unavailable even if file existed
    assert up.source == "uploaded"


# --------------------------------------------------------------------------- #
# JobRepository                                                                #
# --------------------------------------------------------------------------- #
def test_job_lifecycle_and_cancel(db):
    from app.repositories.jobs import JobRepository

    repo = JobRepository(db)
    job = repo.create("evaluate", {"model_id": "small"})
    assert job.status == "queued"
    repo.mark_running(job.id)
    repo.set_progress(job.id, "running val", 0.5)
    repo.mark_succeeded(job.id, {"map50": 0.9})
    done = repo.get(job.id)
    assert done.status == "succeeded"
    assert done.progress == 1.0
    assert done.result_json["map50"] == 0.9


def test_queued_job_cancel_is_immediate(db):
    from app.repositories.jobs import JobRepository

    repo = JobRepository(db)
    job = repo.create("evaluate", {})
    repo.request_cancel(job.id)
    assert repo.get(job.id).status == "cancelled"


def test_reconcile_orphans(db):
    from app.repositories.jobs import JobRepository

    repo = JobRepository(db)
    a = repo.create("evaluate", {})
    repo.mark_running(a.id)
    assert repo.reconcile_orphans() == 1
    assert repo.get(a.id).status == "failed"


def test_mark_running_is_a_guarded_cas(db):
    """mark_running is a compare-and-swap: it transitions ONLY a still-queued job and
    returns the row count, so a cancel that landed first wins and the worker aborts."""
    from app.repositories.jobs import JobRepository

    repo = JobRepository(db)
    # Happy path: queued -> running returns 1.
    job = repo.create("evaluate", {})
    assert repo.mark_running(job.id) == 1
    assert repo.get(job.id).status == "running"

    # Race: a queued job cancelled before the worker calls mark_running -> 0 rows,
    # status stays cancelled (the runner uses this 0 to skip running the job).
    other = repo.create("evaluate", {})
    repo.request_cancel(other.id)
    assert repo.get(other.id).status == "cancelled"
    assert repo.mark_running(other.id) == 0
    assert repo.get(other.id).status == "cancelled"


def test_delete_dismisses_terminal_job_only(db):
    """delete() removes a finished job and returns its id, refuses an active one with
    the 'active' sentinel (so the endpoint can 409 it), and returns None for unknown."""
    from app.repositories.jobs import JobRepository

    repo = JobRepository(db)
    running = repo.create("evaluate", {})
    repo.mark_running(running.id)
    assert repo.delete(running.id) == "active"  # still active -> refused
    assert repo.get(running.id) is not None

    repo.mark_succeeded(running.id, {"map50": 0.9})
    assert repo.delete(running.id) == running.id  # now terminal -> removed
    assert repo.get(running.id) is None

    assert repo.delete("does-not-exist") is None


def test_delete_terminal_clears_finished_keeps_active(db):
    """delete_terminal() bulk-clears finished/failed/cancelled jobs (optionally by kind)
    and leaves queued/running jobs in place."""
    from app.repositories.jobs import JobRepository

    repo = JobRepository(db)
    done = repo.create("evaluate", {})
    repo.mark_succeeded(done.id, {})
    failed = repo.create("evaluate", {})
    repo.mark_failed(failed.id, "boom")
    active = repo.create("label_assist", {})
    repo.mark_running(active.id)
    other_kind_done = repo.create("label_assist", {})
    repo.mark_succeeded(other_kind_done.id, {})

    # Kind-scoped clear removes only finished evaluate jobs.
    assert repo.delete_terminal(kind="evaluate") == 2
    assert repo.get(done.id) is None and repo.get(failed.id) is None
    assert repo.get(active.id) is not None  # still running
    assert repo.get(other_kind_done.id) is not None  # other kind untouched

    # Unscoped clear removes the remaining terminal job, still leaving the active one.
    assert repo.delete_terminal() == 1
    assert repo.get(other_kind_done.id) is None
    assert repo.get(active.id) is not None


def test_seed_project_datasets_registers_in_place(db, tmp_path):
    """Existing on-disk datasets are registered IN PLACE as source='project' rows:
    a standard images/<split> dataset is counted by image files, and a txt-list-split
    dataset (which ultralytics reads natively) is counted by list lines. Idempotent."""
    from types import SimpleNamespace

    from app.repositories.datasets import DatasetRepository, ProtectedDatasetError
    from app.services.datasets_seed import seed_project_datasets

    # Standard layout (2-class detector): images/{train,val,test} dirs.
    det = tmp_path / "papi-2class-detection-flightsplit"
    for split, n in (("train", 2), ("val", 1), ("test", 1)):
        d = det / "images" / split
        d.mkdir(parents=True)
        for i in range(n):
            (d / f"f{i}.jpg").write_bytes(b"x")
    (det / "data.yaml").write_text(
        f"path: {det}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: papi_light_red\n  1: papi_light_white\n",
        encoding="utf-8",
    )

    # Txt-list layout (3-class transition): train.txt/val.txt/test.txt list files.
    tr = tmp_path / "transition-classification-data" / "transition_combined"
    tr.mkdir(parents=True)
    (tr / "train.txt").write_text("a.jpg\nb.jpg\nc.jpg\n", encoding="utf-8")
    (tr / "val.txt").write_text("d.jpg\n", encoding="utf-8")
    (tr / "test.txt").write_text("e.jpg\n", encoding="utf-8")
    (tr / "data.yaml").write_text(
        f"path: {tr}\ntrain: train.txt\nval: val.txt\ntest: test.txt\n"
        "names:\n  0: papi_light_red\n  1: papi_light_white\n  2: papi_light_transition\n",
        encoding="utf-8",
    )

    settings = SimpleNamespace(project_datasets_dir=tmp_path)
    assert seed_project_datasets(settings, db) == 2

    repo = DatasetRepository(db)
    detector = repo.get("project-2class-detector")
    assert detector.source == "project" and detector.status == "ready"
    assert (detector.n_train, detector.n_val, detector.n_test) == (2, 1, 1)  # counted by files
    assert detector.class_names_json == {"0": "papi_light_red", "1": "papi_light_white"}
    assert detector.storage_path == str(det.resolve())

    transition = repo.get("project-transition-3class")
    assert (transition.n_train, transition.n_val, transition.n_test) == (3, 1, 1)  # counted by txt lines
    assert len(transition.class_names_json) == 3

    # Idempotent: a second run registers nothing new.
    assert seed_project_datasets(settings, db) == 0

    # Project datasets are protected from deletion (they point at out-of-volume data).
    with pytest.raises(ProtectedDatasetError):
        repo.delete("project-2class-detector")


def test_seed_project_datasets_skips_when_absent(db, tmp_path):
    """A deployment without the gitignored data/datasets tree (fresh clone / Docker)
    seeds nothing and never raises."""
    from types import SimpleNamespace

    from app.services.datasets_seed import seed_project_datasets

    assert seed_project_datasets(SimpleNamespace(project_datasets_dir=tmp_path), db) == 0


# --------------------------------------------------------------------------- #
# Dataset helpers + bundle ingestion                                          #
# --------------------------------------------------------------------------- #
def test_safe_run_name_neutralises_shell_metacharacters():
    """The run name is interpolated into a copy-paste shell command, so dangerous
    characters must be stripped, the result bounded, and empties given a safe default."""
    from app.services.training_prepare import _safe_run_name, build_command

    assert _safe_run_name("papi train; rm -rf /") == "papi-train-rm--rf"
    assert _safe_run_name("$(whoami)`id`|cat") == "whoami-id-cat"
    assert _safe_run_name("好 emoji 🚀 name") == "emoji-name"
    assert _safe_run_name("!!!") == "papi-train"  # all-unsafe -> default
    assert _safe_run_name("") == "papi-train"
    assert len(_safe_run_name("x" * 200)) <= 64
    # The cleaned name is what lands in the command string (no raw metacharacters).
    cmd = build_command(
        base="yolo26s.pt", epochs=1, imgsz=640, batch=2, oversample=4, name="a; rm b", class_count=3
    )
    assert "; rm" not in cmd
    assert "--name a-rm-b" in cmd

    # Trainer routing by class count (audit 2026-06-19): a 3-class dataset uses the
    # transition trainer; a 2-class dataset uses the detector trainer with its data.yaml
    # and no --oversample (wiring everything to the transition trainer mislabels 2-class
    # detector bundles).
    transition_cmd = build_command(
        base="yolo26s.pt", epochs=1, imgsz=640, batch=2, oversample=4, name="t", class_count=3
    )
    assert "train_transition_model.py" in transition_cmd
    assert "--combined ./dataset" in transition_cmd
    assert "--oversample 4" in transition_cmd
    detector_cmd = build_command(
        base="yolo26s.pt", epochs=1, imgsz=640, batch=2, oversample=4, name="d", class_count=2
    )
    assert "train_detector_model.py" in detector_cmd
    assert "--data ./dataset/data.yaml" in detector_cmd
    assert "--oversample" not in detector_cmd


def test_parse_yolo_label_line_validates():
    from app.services.datasets import parse_yolo_label_line

    assert parse_yolo_label_line("0 0.5 0.5 0.1 0.1", 2) == (0, 0.5, 0.5, 0.1, 0.1)
    assert parse_yolo_label_line("   ", 2) is None
    with pytest.raises(ValueError):
        parse_yolo_label_line("0 0.5 0.5 0.1", 2)  # too few fields
    with pytest.raises(ValueError):
        parse_yolo_label_line("5 0.5 0.5 0.1 0.1", 2)  # class out of range
    with pytest.raises(ValueError):
        parse_yolo_label_line("0 1.5 0.5 0.1 0.1", 2)  # coord out of range


def test_split_for_name_is_stable():
    from app.services.datasets import split_for_name

    name = "frame_001.jpg"
    assert split_for_name(name) == split_for_name(name)
    assert split_for_name(name) in ("train", "val", "test")


def _make_bundle(tmp_path: Path) -> Path:
    """A tiny valid YOLO bundle zip: one labelled image under images/train."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.yaml", "names:\n  0: papi_light_red\n  1: papi_light_white\n")
        zf.writestr("images/train/a.jpg", b"\xff\xd8\xff\xe0fakejpeg")
        zf.writestr("labels/train/a.txt", "0 0.5 0.5 0.1 0.1\n")
        zf.writestr("images/val/b.jpg", b"\xff\xd8\xff\xe0fakejpeg")
        zf.writestr("labels/val/b.txt", "1 0.4 0.4 0.2 0.2\n")
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(buf.getvalue())
    return zip_path


def test_ingest_bundle_normalizes_layout(tmp_path):
    from app.services.dataset_bundle import ingest_bundle

    bundle = _make_bundle(tmp_path)
    root = tmp_path / "ds"
    root.mkdir()
    result = ingest_bundle(bundle, root)
    assert result["class_names"][0] == "papi_light_red"
    assert result["n_train"] == 1 and result["n_val"] == 1
    assert (root / "data.yaml").is_file()
    assert (root / "train.txt").read_text().strip() == "./images/train/a.jpg"
    # _raw scratch is cleaned up.
    assert not (root / "_raw").exists()


def test_ingest_bundle_rejects_zip_slip(tmp_path):
    # A traversal member rejects the whole bundle.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.jpg", b"\xff\xd8\xff\xe0x")
    bundle = tmp_path / "evil.zip"
    bundle.write_bytes(buf.getvalue())
    root = tmp_path / "ds"
    root.mkdir()
    from app.services.dataset_bundle import ingest_bundle

    with pytest.raises(ValueError):
        ingest_bundle(bundle, root)
    assert not (tmp_path / "evil.jpg").exists()  # never written outside root


def test_ingest_bundle_rejects_mixed_zip_slip(tmp_path):
    """A bundle with valid data plus a traversal member is rejected, not partially accepted."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.yaml", "names:\n  0: red\n")
        zf.writestr("images/train/a.jpg", b"\xff\xd8\xff\xe0x")
        zf.writestr("labels/train/a.txt", "0 0.5 0.5 0.1 0.1\n")
        zf.writestr("../evil.jpg", b"\xff\xd8\xff\xe0x")
    bundle = tmp_path / "mixed-evil.zip"
    bundle.write_bytes(buf.getvalue())
    root = tmp_path / "ds"
    root.mkdir()

    from app.services.dataset_bundle import ingest_bundle

    with pytest.raises(ValueError, match="unsafe path"):
        ingest_bundle(bundle, root)
    assert not (tmp_path / "evil.jpg").exists()
    assert not (root / "images" / "train" / "a.jpg").exists()


# --------------------------------------------------------------------------- #
# Evaluation metric mapping (no GPU)                                           #
# --------------------------------------------------------------------------- #
def test_evaluate_to_val_metrics_uses_ap_class_index():
    from app.services.jobs.handlers.evaluate import _to_val_metrics

    # Only class 1 present in the split; ap_class_index drives naming, not position.
    box = SimpleNamespace(
        mp=0.9, mr=0.8, map50=0.85, map=0.5,
        p=[0.9], r=[0.8], ap50=[0.95], ap_class_index=[1],
    )
    metrics = SimpleNamespace(box=box)
    result = _to_val_metrics(metrics, {0: "red", 1: "white"}, "test")
    assert "white" in result["per_class"]
    assert "red" not in result["per_class"]  # absent class not fabricated


def test_evaluate_to_val_metrics_handles_numpy_ap_class_index():
    """ap_class_index is a numpy array at runtime; the old ``array or []`` raised
    'truth value of an array is ambiguous', crashing every real evaluation. The list
    stub above never caught it — this pins the numpy path (regression)."""
    import numpy as np
    from app.services.jobs.handlers.evaluate import _to_val_metrics

    # Position order follows ap_class_index: red=class 0 (pos 0), white=class 1 (pos 1).
    # White carries p=0.9/r=0.8 so its f1 is f1(0.9, 0.8).
    box = SimpleNamespace(
        mp=0.9, mr=0.8, map50=0.85, map=0.5,
        p=np.array([0.7, 0.9]), r=np.array([0.6, 0.8]),
        ap50=np.array([0.9, 0.95]), ap_class_index=np.array([0, 1]),
    )
    result = _to_val_metrics(SimpleNamespace(box=box), {0: "red", 1: "white"}, "test")
    assert set(result["per_class"]) == {"red", "white"}
    assert result["precision"] == 0.9
    assert result["map50"] == 0.85
    assert result["per_class"]["white"]["f1"] == pytest.approx(2 * 0.9 * 0.8 / (0.9 + 0.8), rel=1e-3)


# --------------------------------------------------------------------------- #
# HTTP layer (shared in-memory DB + fake runner + mocked weight load)         #
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAPI_USER_MODELS_DIR", str(tmp_path / "user_models"))
    monkeypatch.setenv("PAPI_DATASETS_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("PAPI_JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv("PAPI_STORAGE_DIR", str(tmp_path / "storage"))

    from app.config import get_settings
    from app.database import get_engine, get_sessionmaker, init_db
    from app.services.inference import get_inference_service
    from app.services.jobs.runner import get_job_runner

    caches = [get_settings, get_engine, get_sessionmaker, get_inference_service, get_job_runner]
    for fn in caches:
        fn.cache_clear()
    init_db()

    # Seed the registry from the frozen JSON loader so /api/models has built-ins.
    from app.repositories.model_registry import ModelRegistryRepository
    from app.services.model_registry import load_model_registry

    s = get_sessionmaker()()
    try:
        ModelRegistryRepository(s).seed_from_frozen(load_model_registry(get_settings()))
    finally:
        s.close()

    # Fake the runner so submit() just records a queued job (no YOLO, no threads).
    from app.repositories.jobs import JobRepository

    def fake_submit(kind, params):
        sess = get_sessionmaker()()
        try:
            return JobRepository(sess).create(kind, params).id
        finally:
            sess.close()

    monkeypatch.setattr(get_job_runner(), "submit", fake_submit)

    from app.main import app
    from fastapi.testclient import TestClient

    yield TestClient(app)

    for fn in caches:
        fn.cache_clear()


def test_models_list_includes_seeded_builtins(client):
    resp = client.get("/api/models")
    assert resp.status_code == 200
    ids = {m["model_id"] for m in resp.json()}
    assert "small" in ids
    small = next(m for m in resp.json() if m["model_id"] == "small")
    assert small["protected"] is True
    assert small["source"] == "builtin"


def test_upload_model_registers_and_is_selectable(client, monkeypatch, tmp_path):
    # Mock the YOLO test-load so no real weights are needed.
    monkeypatch.setattr(
        "app.services.model_upload.test_load_weights",
        lambda path: (2, {0: "PAPI-Red", 1: "PAPI-White"}),
    )
    files = {"file": ("my_model.pt", b"PK\x03\x04fake-checkpoint", "application/octet-stream")}
    resp = client.post("/api/models", files=files, data={"label": "My model", "role": "detector"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "uploaded"
    assert body["model_label"] == "My model"
    # It now appears in the registry list.
    assert any(m["model_label"] == "My model" for m in client.get("/api/models").json())


def test_upload_rejects_bad_suffix(client):
    files = {"file": ("notamodel.txt", b"hello", "text/plain")}
    resp = client.post("/api/models", files=files, data={"label": "x"})
    assert resp.status_code == 400


def test_upload_rejects_bad_pt_signature(client):
    files = {"file": ("m.pt", b"not-a-checkpoint", "application/octet-stream")}
    resp = client.post("/api/models", files=files, data={"label": "x"})
    assert resp.status_code == 400


def test_delete_protected_model_returns_400(client):
    assert client.delete("/api/models/small").status_code == 400


def test_promote_uploaded_model(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.model_upload.test_load_weights", lambda path: (2, {0: "r", 1: "w"})
    )
    files = {"file": ("m.pt", b"PK\x03\x04fake", "application/octet-stream")}
    new_id = client.post("/api/models", files=files, data={"label": "Promote me"}).json()["model_id"]
    resp = client.post(f"/api/models/{new_id}/promote")
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True


def test_dismiss_and_clear_jobs_endpoints(client):
    """DELETE /api/jobs/{id} dismisses a finished job (404 unknown, 409 active);
    DELETE /api/jobs bulk-clears finished jobs (optionally by kind), leaving active ones."""
    from app.database import get_sessionmaker
    from app.repositories.jobs import JobRepository

    s = get_sessionmaker()()
    try:
        repo = JobRepository(s)
        active = repo.create("evaluate", {})
        active_id = active.id
        repo.mark_running(active.id)
        done = repo.create("evaluate", {})
        done_id = done.id
        repo.mark_succeeded(done.id, {})
    finally:
        s.close()

    # Unknown -> 404; still-active -> 409 (must cancel first); finished -> 204.
    assert client.delete("/api/jobs/nope").status_code == 404
    assert client.delete(f"/api/jobs/{active_id}").status_code == 409
    assert client.delete(f"/api/jobs/{done_id}").status_code == 204
    assert all(j["id"] != done_id for j in client.get("/api/jobs").json())

    # Bulk clear of finished evaluate jobs leaves the active one in place.
    s = get_sessionmaker()()
    try:
        repo = JobRepository(s)
        repo.mark_succeeded(repo.create("evaluate", {}).id, {})
    finally:
        s.close()
    resp = client.delete("/api/jobs?kind=evaluate")
    assert resp.status_code == 200
    assert resp.json()["deleted"] >= 1
    assert active_id in {j["id"] for j in client.get("/api/jobs").json()}


def test_dataset_bundle_upload(client, tmp_path):
    bundle = _make_bundle(tmp_path)
    with bundle.open("rb") as fh:
        resp = client.post(
            "/api/datasets", files={"file": ("bundle.zip", fh, "application/zip")},
            data={"name": "My dataset"},
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["n_train"] == 1 and body["n_val"] == 1


def test_assisted_labeling_enqueues_job(client):
    resp = client.post(
        "/api/datasets/assisted",
        files=[
            ("files", ("frame_001.jpg", b"\xff\xd8\xff" + b"\x00" * 256, "image/jpeg")),
            ("files", ("frame_002.jpg", b"\xff\xd8\xff" + b"\x00" * 256, "image/jpeg")),
        ],
        data={"name": "assist", "model_id": "small"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["n_images"] == 2
    assert body["job_id"]
    datasets = client.get("/api/datasets").json()
    assert datasets[0]["id"] == body["dataset_id"]
    assert datasets[0]["status"] == "labeling"


def test_assisted_labeling_caps_batch_size(client, monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PAPI_MAX_BATCH_FRAMES", "3")
    try:
        files = [
            ("files", (f"frame_{i:03d}.jpg", b"\xff\xd8\xff" + b"\x00" * 256, "image/jpeg"))
            for i in range(4)
        ]
        resp = client.post(
            "/api/datasets/assisted",
            files=files,
            data={"name": "assist", "model_id": "small"},
        )
        assert resp.status_code == 413
        assert "limited to 3 images" in resp.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_assisted_labeling_caps_aggregate_upload_size(client, monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("PAPI_MAX_UPLOAD_MB", "2")
    monkeypatch.setenv("PAPI_MAX_BATCH_UPLOAD_MB", "1")
    try:
        files = [
            ("files", ("frame_001.jpg", b"\xff\xd8\xff" + b"x" * 700_000, "image/jpeg")),
            ("files", ("frame_002.jpg", b"\xff\xd8\xff" + b"x" * 700_000, "image/jpeg")),
        ]
        resp = client.post(
            "/api/datasets/assisted",
            files=files,
            data={"name": "assist", "model_id": "small"},
        )
        assert resp.status_code == 413
        assert "limited to 1 MB total" in resp.json()["detail"]
    finally:
        get_settings.cache_clear()


def test_assisted_labeling_rejects_bad_file_without_orphan(client):
    resp = client.post(
        "/api/datasets/assisted",
        files=[
            ("files", ("frame_001.jpg", b"\xff\xd8\xff" + b"\x00" * 256, "image/jpeg")),
            ("files", ("notes.txt", b"not an image", "text/plain")),
        ],
        data={"name": "assist", "model_id": "small"},
    )
    assert resp.status_code == 400
    assert client.get("/api/datasets").json() == []


def test_evaluate_enqueues_job(client):
    bundle_data = io.BytesIO()
    with zipfile.ZipFile(bundle_data, "w") as zf:
        zf.writestr("data.yaml", "names:\n  0: red\n  1: white\n")
        zf.writestr("images/test/a.jpg", b"\xff\xd8\xff\xe0x")
        zf.writestr("labels/test/a.txt", "0 0.5 0.5 0.1 0.1\n")
    resp = client.post(
        "/api/datasets",
        files={"file": ("b.zip", bundle_data.getvalue(), "application/zip")},
        data={"name": "evalds"},
    )
    dataset_id = resp.json()["id"]
    job = client.post("/api/models/small/evaluate", json={"dataset_id": dataset_id, "split": "test"})
    assert job.status_code == 200, job.text
    assert job.json()["kind"] == "evaluate"
    assert job.json()["status"] == "queued"


def test_evaluate_rejects_ready_dataset_with_missing_files(client):
    # A row can be 'ready' while its data.yaml is absent on this node (e.g. a built-in
    # seeded into a shared DB whose files landed elsewhere). The endpoint must reject
    # with a clear 400 up front, not enqueue a job that dies as "no data.yaml".
    from app.database import get_sessionmaker
    from app.repositories.datasets import DatasetRepository

    session = get_sessionmaker()()
    try:
        ghost = DatasetRepository(session).create(
            name="ghost", source="builtin", status="ready",
            storage_path="/does/not/exist", class_names={0: "red", 1: "white"},
        )
        ghost_id = ghost.id
    finally:
        session.close()

    resp = client.post("/api/models/small/evaluate", json={"dataset_id": ghost_id, "split": "test"})
    assert resp.status_code == 400, resp.text
    assert "data.yaml" in resp.json()["detail"]


def test_evaluate_rejects_train_split(client):
    # Literal["test","val"] rejects 'train' at request validation (422), so a caller
    # cannot write training-split metrics back to the model card.
    resp = client.post("/api/models/small/evaluate", json={"dataset_id": "x", "split": "train"})
    assert resp.status_code == 422


def test_bundle_corrupt_zip_returns_400_without_orphan(client):
    # Valid PK signature but a truncated/garbage body: passes is_zip, fails extraction
    # with BadZipFile -> must be a clean 400 and leave no dataset row behind.
    corrupt = b"PK\x03\x04" + b"\x00" * 32
    resp = client.post(
        "/api/datasets",
        files={"file": ("bad.zip", corrupt, "application/zip")},
        data={"name": "corrupt"},
    )
    assert resp.status_code == 400
    assert client.get("/api/datasets").json() == []


def test_ingest_bundle_extract_cap_aborts(tmp_path):
    from app.services.dataset_bundle import ingest_bundle

    bundle = _make_bundle(tmp_path)
    root = tmp_path / "capped"
    root.mkdir()
    # A 1-byte extraction budget must trip the zip-bomb guard.
    with pytest.raises(ValueError):
        ingest_bundle(bundle, root, max_extract_bytes=1)


def test_api_key_gates_mutations(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("PAPI_API_KEY", "secret")
    monkeypatch.setenv("PAPI_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("PAPI_USER_MODELS_DIR", str(tmp_path / "um"))
    monkeypatch.setenv("PAPI_DATASETS_DIR", str(tmp_path / "ds"))
    monkeypatch.setenv("PAPI_JOBS_DIR", str(tmp_path / "jobs"))

    from app.config import get_settings
    from app.database import get_engine, get_sessionmaker, init_db
    from app.services.inference import get_inference_service

    caches = [get_settings, get_engine, get_sessionmaker, get_inference_service]
    for fn in caches:
        fn.cache_clear()
    init_db()

    from app.main import app
    from fastapi.testclient import TestClient

    c = TestClient(app)
    try:
        # No key -> 401 on a gated read and a gated mutation.
        assert c.get("/api/models").status_code == 401
        assert c.delete("/api/models/small").status_code == 401
        # Correct key -> the read is allowed (200).
        assert c.get("/api/models", headers={"X-API-Key": "secret"}).status_code == 200
    finally:
        for fn in caches:
            fn.cache_clear()
