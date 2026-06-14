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


# --------------------------------------------------------------------------- #
# Dataset helpers + bundle ingestion                                          #
# --------------------------------------------------------------------------- #
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
