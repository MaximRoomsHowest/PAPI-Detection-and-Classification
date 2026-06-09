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
