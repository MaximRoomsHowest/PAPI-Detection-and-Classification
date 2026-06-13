"""InferenceService._resolve_selected_model: the (model, entry, method) selection matrix.

This is the branch-heaviest logic the model registry added and the path every analyze
request goes through; audit TRN-1 slipped through a green suite precisely because none
of these contracts were pinned (audit TEST-1/DT-3).
"""

import json
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.services.inference.service import InferenceService

TWO_CLASS = SimpleNamespace(names={0: "papi_light_red", 1: "papi_light_white"})
THREE_CLASS = SimpleNamespace(names={0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"})


def _service(tmp_path, monkeypatch, *, transition_exists=True, default_transition_method="tracking"):
    serving = tmp_path / "models" / "serving"
    serving.mkdir(parents=True)
    small = serving / "best.pt"
    small.write_bytes(b"small")
    transition = tmp_path / "models" / "runs" / "transition" / "weights" / "best.pt"
    if transition_exists:
        transition.parent.mkdir(parents=True)
        transition.write_bytes(b"transition")
    registry_path = serving / "models.json"
    registry_path.write_text(
        json.dumps(
            {
                "default_model_id": "small",
                "models": [
                    {"id": "small", "role": "detector", "path": "models/serving/best.pt", "class_count": 2, "default": True},
                    {
                        "id": "transition",
                        "role": "transition",
                        "path": "models/runs/transition/weights/best.pt",
                        "class_count": 3,
                        "disabled_reason": "transition checkpoint not installed",
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
        default_transition_method=default_transition_method,
    )
    service = InferenceService(settings)
    # Stub the heavy YOLO load: hand back a class-count-appropriate fake model.
    monkeypatch.setattr(
        InferenceService,
        "_load_model",
        lambda self, entry: THREE_CLASS if entry.class_count >= 3 else TWO_CLASS,
    )
    return service


def test_unknown_model_id_raises_value_error(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Unknown model_id"):
        service._resolve_selected_model("nope", None)


def test_unavailable_model_id_raises_with_disabled_reason(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch, transition_exists=False)
    with pytest.raises(ValueError, match="transition checkpoint not installed"):
        service._resolve_selected_model("transition", None)


def test_explicit_transition_model_defaults_to_model_method(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    model, entry, method = service._resolve_selected_model("transition", None)
    assert (entry.id, method, model) == ("transition", "model", THREE_CLASS)


def test_explicit_two_class_model_with_model_method_degrades_to_tracking(tmp_path, monkeypatch):
    """Explicit model choice wins; a 2-class model cannot run the 'model' method."""
    service = _service(tmp_path, monkeypatch)
    model, entry, method = service._resolve_selected_model("small", "model")
    assert (entry.id, method, model) == ("small", "tracking", TWO_CLASS)


def test_omitted_everything_uses_default_entry_and_tracking(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    model, entry, method = service._resolve_selected_model(None, None)
    assert (entry.id, method, model) == ("small", "tracking", TWO_CLASS)


def test_omitted_everything_honours_configured_model_method(tmp_path, monkeypatch):
    """PAPI_TRANSITION_METHOD=model must reach the live request path (audit TRN-1)."""
    service = _service(tmp_path, monkeypatch, default_transition_method="model")
    model, entry, method = service._resolve_selected_model(None, None)
    assert (entry.id, method, model) == ("transition", "model", THREE_CLASS)


def test_configured_model_method_falls_back_when_transition_missing(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch, transition_exists=False, default_transition_method="model")
    monkeypatch.setattr(InferenceService, "model", property(lambda self: TWO_CLASS))
    monkeypatch.setattr(InferenceService, "transition_model", property(lambda self: None))
    model, entry, method = service._resolve_selected_model(None, None)
    assert (entry.id, method) == ("small", "tracking")


def test_explicit_tracking_is_honoured(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch, default_transition_method="model")
    model, entry, method = service._resolve_selected_model(None, "tracking")
    assert (entry.id, method) == ("small", "tracking")


def test_explicit_model_method_without_model_id_uses_transition_entry(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    model, entry, method = service._resolve_selected_model(None, "model")
    assert (entry.id, method, model) == ("transition", "model", THREE_CLASS)


def test_invalid_explicit_transition_method_is_rejected(tmp_path, monkeypatch):
    service = _service(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="transition_method must be 'tracking' or 'model'"):
        service._resolve_selected_model(None, "banana")
    with pytest.raises(ValueError, match="transition_method must be 'tracking' or 'model'"):
        service._resolve_selected_model("small", "banana")
