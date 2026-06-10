import hashlib
import json

from app.config import Settings
from app.services.inference import InferenceService
from app.services.model_registry import compute_sha256, load_model_card, load_model_registry


def test_compute_sha256_matches_hashlib(tmp_path):
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-bytes")
    assert compute_sha256(weights) == hashlib.sha256(b"weights-bytes").hexdigest()


def test_compute_sha256_missing_file_is_none(tmp_path):
    assert compute_sha256(tmp_path / "nope.pt") is None


def test_load_model_card_reads_sibling_json(tmp_path):
    model_path = tmp_path / "serving" / "best.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"x")
    (model_path.parent / "model_card.json").write_text(
        json.dumps({"model_id": "demo", "training_run": "run-x"}), encoding="utf-8"
    )
    card = load_model_card(model_path)
    assert card is not None
    assert card["model_id"] == "demo"
    assert card["training_run"] == "run-x"


def test_load_model_card_absent_is_none(tmp_path):
    model_path = tmp_path / "best.pt"
    model_path.write_bytes(b"x")
    assert load_model_card(model_path) is None


def test_model_info_surfaces_provenance_from_card(tmp_path):
    model_path = tmp_path / "serving" / "best.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"fake-weights")
    (model_path.parent / "model_card.json").write_text(
        json.dumps(
            {
                "model_id": "yolo26n-demo",
                "training_run": "run-demo",
                "base_weights": "yolo26n.pt",
                "split_evaluated": "val",
                "val_metrics": {
                    "selection": "best_fitness_epoch",
                    "epoch": 30,
                    "precision": 0.86,
                    "recall": 0.87,
                    "map50": 0.91,
                    "map50_95": 0.47,
                    "note": "val-split box metrics",
                },
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=model_path,
        model_registry_path=tmp_path / "missing-registry.json",
    )

    info = InferenceService(settings).model_info()

    assert info.sha256 == hashlib.sha256(b"fake-weights").hexdigest()
    assert info.model_id == "default"
    assert info.model_card_id == "yolo26n-demo"
    assert info.training_run == "run-demo"
    assert info.dataset_split_evaluated == "val"
    assert info.val_metrics is not None
    assert info.val_metrics.map50_95 == 0.47
    # provenance is available even though the heavy model was never loaded
    assert info.loaded is False


def test_model_info_without_card_returns_none_provenance(tmp_path):
    model_path = tmp_path / "serving" / "best.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"fake-weights")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=model_path,
        model_registry_path=tmp_path / "missing-registry.json",
    )

    info = InferenceService(settings).model_info()

    assert info.training_run is None
    assert info.val_metrics is None
    # sha256 is still computed from the on-disk file
    assert info.sha256 == hashlib.sha256(b"fake-weights").hexdigest()


def test_device_explicit_value_is_used_verbatim(tmp_path):
    settings = Settings(storage_dir=tmp_path / "s", model_path=tmp_path / "best.pt", device="cpu")
    # An explicit device is returned as-is and never imports torch (audit IMP-SRV-2).
    assert InferenceService(settings).device == "cpu"


def test_device_auto_resolves_to_a_real_device(tmp_path):
    settings = Settings(storage_dir=tmp_path / "s", model_path=tmp_path / "best.pt", device="auto")
    # 'auto' must resolve to a concrete device (cpu in CI; cuda only if a GPU exists).
    assert InferenceService(settings).device in {"cpu", "cuda"}


def test_load_model_registry_reads_configured_models_and_resolves_paths(tmp_path):
    models_root = tmp_path / "models"
    serving = models_root / "serving"
    serving.mkdir(parents=True)
    small = serving / "best.pt"
    small.write_bytes(b"small")
    nano = models_root / "runs" / "nano" / "weights" / "best.pt"
    nano.parent.mkdir(parents=True)
    nano.write_bytes(b"nano")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": "small",
                "models": [
                    {"id": "small", "label": "Small", "role": "detector", "path": "models/serving/best.pt", "default": True},
                    {"id": "nano", "label": "Nano", "role": "detector", "path": "models/runs/nano/weights/best.pt"},
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=small,
        model_registry_path=registry_path,
    )

    registry = load_model_registry(settings)

    assert registry.default_model_id == "small"
    assert registry.get("small").path == small
    assert registry.get("nano").path == nano
    assert registry.get("nano").available is True


def test_load_model_registry_marks_missing_transition_unavailable(tmp_path):
    serving = tmp_path / "models" / "serving"
    serving.mkdir(parents=True)
    small = serving / "best.pt"
    small.write_bytes(b"small")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": "small",
                "models": [
                    {"id": "small", "label": "Small", "role": "detector", "path": "models/serving/best.pt", "default": True},
                    {
                        "id": "transition",
                        "label": "Transition",
                        "role": "transition",
                        "path": "data/runs/missing/weights/best.pt",
                        "class_count": 3,
                        "disabled_reason": "missing transition checkpoint",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=small,
        model_registry_path=registry_path,
    )

    transition = load_model_registry(settings).get("transition")

    assert transition.available is False
    assert transition.disabled_reason == "missing transition checkpoint"


def test_load_model_registry_skips_malformed_entry_instead_of_crashing(tmp_path):
    """One bad scalar must cost one entry, not every endpoint (audit REG-1)."""
    serving = tmp_path / "models" / "serving"
    serving.mkdir(parents=True)
    small = serving / "best.pt"
    small.write_bytes(b"small")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": "small",
                "models": [
                    {"id": "broken", "role": "detector", "path": "models/serving/best.pt", "class_count": "two"},
                    {"id": "small", "label": "Small", "role": "detector", "path": "models/serving/best.pt", "default": True},
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=small,
        model_registry_path=registry_path,
    )

    registry = load_model_registry(settings)

    assert [entry.id for entry in registry.entries] == ["small"]
    assert registry.default_model_id == "small"


def test_model_options_degrade_on_malformed_val_metrics(tmp_path):
    """A wrong-typed optional metadata field nulls that field; it must not 500
    the whole /api/models selector list (audit REG-2)."""
    serving = tmp_path / "models" / "serving"
    serving.mkdir(parents=True)
    small = serving / "best.pt"
    small.write_bytes(b"small")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": "small",
                "models": [
                    {
                        "id": "small",
                        "label": "Small",
                        "role": "detector",
                        "path": "models/serving/best.pt",
                        "default": True,
                        "val_metrics": {"map50": "not-a-number"},
                        "classes": {"zero": "PAPI-Red"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=small,
        model_registry_path=registry_path,
    )

    options = InferenceService(settings).model_options()

    assert len(options) == 1
    assert options[0].val_metrics is None
    assert options[0].classes is None


def test_shipped_models_json_loads_and_keeps_per_class_metrics():
    """Smoke-load the real committed registry (audit DT-5): every entry parses and
    the transition entry's per-class metrics — its most honest numbers — survive
    schema validation instead of being silently dropped."""
    from app.config import REPO_ROOT

    registry_file = REPO_ROOT / "models" / "serving" / "models.json"
    settings = Settings(
        storage_dir=REPO_ROOT / "apps" / "backend" / "storage",
        model_path=REPO_ROOT / "models" / "serving" / "best.pt",
        model_registry_path=registry_file,
    )

    options = InferenceService(settings).model_options()

    assert {opt.model_id for opt in options} >= {"small", "nano", "transition"}
    transition = next(opt for opt in options if opt.model_id == "transition")
    assert transition.val_metrics is not None
    assert transition.val_metrics.per_class is not None
    assert "transition" in transition.val_metrics.per_class


def test_model_info_reports_load_time_sha_after_disk_swap(tmp_path):
    """The digest must describe the weights in memory; compose mounts ./models so the
    file can be swapped under a running service (audit SHA-1)."""
    model_path = tmp_path / "serving" / "best.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"original-weights")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=model_path,
        model_registry_path=tmp_path / "missing-registry.json",
    )
    service = InferenceService(settings)
    original_sha = hashlib.sha256(b"original-weights").hexdigest()
    # Simulate a completed load without pulling in YOLO.
    service._models["default"] = object()
    service._loaded_sha256["default"] = original_sha

    model_path.write_bytes(b"swapped-weights")
    info = service.model_info()

    assert info.loaded is True
    assert info.sha256 == original_sha
    assert info.weights_changed_on_disk is True


def test_preload_available_models_skips_missing_and_survives_failures(tmp_path, monkeypatch):
    """Startup preload loads what it can, logs what it can't, never raises (audit WARM-1)."""
    serving = tmp_path / "models" / "serving"
    serving.mkdir(parents=True)
    small = serving / "best.pt"
    small.write_bytes(b"small")
    nano = tmp_path / "models" / "runs" / "nano" / "weights" / "best.pt"
    nano.parent.mkdir(parents=True)
    nano.write_bytes(b"nano")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": "small",
                "models": [
                    {"id": "small", "role": "detector", "path": "models/serving/best.pt", "default": True},
                    {"id": "nano", "role": "detector", "path": "models/runs/nano/weights/best.pt"},
                    {"id": "transition", "role": "transition", "path": "models/runs/missing/best.pt", "class_count": 3},
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=small,
        model_registry_path=registry_path,
    )
    service = InferenceService(settings)

    def fake_load(self, entry):
        if entry.id == "nano":
            raise RuntimeError("corrupt checkpoint")
        self._models[entry.id] = object()

    monkeypatch.setattr(InferenceService, "_load_model", fake_load)

    loaded = service.preload_available_models()

    assert loaded == ["small"]  # nano failed (logged), transition skipped (missing)


def _drift_registry(tmp_path, *, default_model_id, flag_on):
    models_root = tmp_path / "models"
    serving = models_root / "serving"
    serving.mkdir(parents=True)
    small = serving / "best.pt"
    small.write_bytes(b"small")
    (serving / "model_card.json").write_text(
        json.dumps({"model_id": "serving-slot-run"}), encoding="utf-8"
    )
    nano = models_root / "runs" / "nano" / "weights" / "best.pt"
    nano.parent.mkdir(parents=True)
    nano.write_bytes(b"nano")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": default_model_id,
                "models": [
                    {"id": "small", "role": "detector", "path": "models/serving/best.pt", "default": flag_on == "small"},
                    {"id": "nano", "role": "detector", "path": "models/runs/nano/weights/best.pt", "default": flag_on == "nano"},
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=small,
        model_registry_path=registry_path,
    )
    return load_model_registry(settings), small, nano


def test_default_flag_drift_does_not_relabel_non_default_entry(tmp_path):
    """A stray "default": true flag previously clobbered THAT entry's path with
    PAPI_MODEL_PATH before default_model_id was resolved — serving one run's weights
    under another run's label (audit DEF-1). The override now keys on the resolved
    default, so the flagged-but-not-default entry keeps its declared path."""
    registry, small, nano = _drift_registry(tmp_path, default_model_id="small", flag_on="nano")

    assert registry.default_model_id == "small"
    assert registry.get("small").path == small
    assert registry.get("nano").path == nano  # not clobbered


def test_resolved_default_gets_model_path_override_and_adjacent_card(tmp_path):
    """When the resolved default's declared path differs from PAPI_MODEL_PATH, the
    override applies to IT (legacy contract) and provenance comes from the card next
    to the real weights, not the registry-inline card (audit DEF-1/SD-1)."""
    registry, small, nano = _drift_registry(tmp_path, default_model_id="nano", flag_on="small")

    default_entry = registry.get()
    assert default_entry.id == "nano"
    assert default_entry.path == small  # PAPI_MODEL_PATH wins for the default
    assert default_entry.card is not None
    assert default_entry.card.get("model_id") == "serving-slot-run"  # adjacent card


def test_load_model_registry_falls_back_to_single_model_when_registry_absent(tmp_path):
    model_path = tmp_path / "best.pt"
    model_path.write_bytes(b"single")
    settings = Settings(
        storage_dir=tmp_path / "storage",
        model_path=model_path,
        model_registry_path=tmp_path / "missing.json",
    )

    registry = load_model_registry(settings)

    assert registry.default_model_id == "default"
    assert registry.get().path == model_path
