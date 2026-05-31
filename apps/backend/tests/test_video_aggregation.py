"""Unit tests for ``InferenceService._aggregate_video_lamps``.

This pure static method turns each lamp's per-frame history (collected across a
video) into the final 4-lamp verdict by majority vote. It drives every video
upload's result yet had no direct coverage — a lamp that flickers red/white, or
is never detected, is exactly where the mode-vote + tie-break is easy to regress.
"""

from app.services.inference import InferenceService
from app.validation.schemas import BoundingBox, LampResult

_aggregate = InferenceService._aggregate_video_lamps


def _lamp(state: str, confidence: float, bbox: BoundingBox | None = None) -> LampResult:
    # index is irrelevant here — _aggregate keys the output off the history dict.
    return LampResult(index=1, state=state, confidence=confidence, bbox=bbox)


def test_aggregate_returns_four_lamps_with_modes_and_unknowns():
    bb = BoundingBox(x1=10, y1=20, x2=30, y2=40)
    history = {
        1: [_lamp("red", 0.8), _lamp("red", 0.6), _lamp("white", 0.9)],
        2: [_lamp("white", 0.5, bb), _lamp("white", 0.7, bb)],
        3: [_lamp("unknown", 0.0)],
        # index 4 absent entirely
    }

    result = _aggregate(history)
    assert [lamp.index for lamp in result] == [1, 2, 3, 4]
    by_index = {lamp.index: lamp for lamp in result}

    # Lamp 1: 2 red vs 1 white -> red; confidence averages ONLY the red frames.
    assert by_index[1].state == "red"
    assert by_index[1].confidence == 0.7

    # Lamp 2: all white; a bbox is carried from a matching frame.
    assert by_index[2].state == "white"
    assert by_index[2].confidence == 0.6
    assert by_index[2].bbox is not None

    # Lamp 3: only 'unknown' observations -> unknown, zero confidence.
    assert by_index[3].state == "unknown"
    assert by_index[3].confidence == 0.0

    # Lamp 4: never observed -> unknown, zero confidence (padded to 4 lamps).
    assert by_index[4].state == "unknown"
    assert by_index[4].confidence == 0.0


def test_aggregate_tie_break_keeps_first_observed_state():
    # Counter.most_common preserves insertion order on ties (CPython 3.7+), so an
    # even red/white split resolves to the first-observed state. Pin that here so
    # the (otherwise silent) tie-break can't drift unnoticed.
    result = _aggregate({1: [_lamp("white", 0.5), _lamp("red", 0.5)], 2: [], 3: [], 4: []})
    assert result[0].state == "white"
    assert result[0].confidence == 0.5
