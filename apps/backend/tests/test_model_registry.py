import hashlib
import json

from app.config import Settings
from app.services.inference import InferenceService
from app.services.model_registry import compute_sha256, load_model_card


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
    settings = Settings(storage_dir=tmp_path / "storage", model_path=model_path)

    info = InferenceService(settings).model_info()

    assert info.sha256 == hashlib.sha256(b"fake-weights").hexdigest()
    assert info.model_id == "yolo26n-demo"
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
    settings = Settings(storage_dir=tmp_path / "storage", model_path=model_path)

    info = InferenceService(settings).model_info()

    assert info.training_run is None
    assert info.val_metrics is None
    # sha256 is still computed from the on-disk file
    assert info.sha256 == hashlib.sha256(b"fake-weights").hexdigest()
