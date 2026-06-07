"""InferenceService._resolve_transition: pick the (model, effective_method) for a request.

The "model" method needs a 3-class detector; it prefers the dedicated transition model, then a
3-class serving model, and otherwise falls back gracefully to "tracking" so a request never fails
just because no 3-class model is installed.
"""

from types import SimpleNamespace

from app.config import get_settings
from app.services.inference.service import InferenceService

TWO_CLASS = SimpleNamespace(names={0: "papi_light_red", 1: "papi_light_white"})
THREE_CLASS = SimpleNamespace(names={0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"})


def _service():
    return InferenceService(get_settings())


def _patch(monkeypatch, *, serving, transition):
    monkeypatch.setattr(InferenceService, "model", property(lambda self: serving))
    monkeypatch.setattr(InferenceService, "transition_model", property(lambda self: transition))


def test_is_three_class():
    assert InferenceService._is_three_class(THREE_CLASS) is True
    assert InferenceService._is_three_class(TWO_CLASS) is False


def test_tracking_uses_serving_model(monkeypatch):
    _patch(monkeypatch, serving=TWO_CLASS, transition=None)
    assert _service()._resolve_transition("tracking") == (TWO_CLASS, "tracking")


def test_model_falls_back_to_tracking_without_a_3class_model(monkeypatch):
    """'model' requested but only a 2-class serving model + no transition model -> graceful fallback."""
    _patch(monkeypatch, serving=TWO_CLASS, transition=None)
    assert _service()._resolve_transition("model") == (TWO_CLASS, "tracking")


def test_model_uses_dedicated_transition_model_when_available(monkeypatch):
    _patch(monkeypatch, serving=TWO_CLASS, transition=THREE_CLASS)
    assert _service()._resolve_transition("model") == (THREE_CLASS, "model")


def test_model_uses_serving_model_when_it_is_itself_3class(monkeypatch):
    """If the serving model is promoted to 3-class, the model method uses it (no separate model)."""
    _patch(monkeypatch, serving=THREE_CLASS, transition=None)
    assert _service()._resolve_transition("model") == (THREE_CLASS, "model")


def test_none_uses_configured_default(monkeypatch):
    """An omitted method uses settings.default_transition_method (default 'tracking')."""
    _patch(monkeypatch, serving=TWO_CLASS, transition=None)
    assert _service()._resolve_transition(None) == (TWO_CLASS, "tracking")
