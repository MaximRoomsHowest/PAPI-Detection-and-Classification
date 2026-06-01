"""Unit tests for ``InferenceService._aggregate_video_lamps``.

This builds the final 4-lamp video verdict from the per-track observation lists
(track_id -> [(frame, color, center_x, confidence)]) by majority vote, keyed off
STABLE ByteTrack identity rather than per-frame left-to-right rank. The identity
choice is the whole point: a dropped/re-ordered frame must not mix observations
of different physical lamps into one bucket.
"""

from app.services.inference import InferenceService

_aggregate = InferenceService._aggregate_video_lamps


def test_aggregate_majority_vote_and_obscured_padding():
    # Three tracks, left-to-right by mean center_x (10 < 20 < 30); track 4 absent.
    obs = {
        101: [(0, "red", 10.0, 0.8), (1, "red", 10.0, 0.6), (2, "white", 10.0, 0.9)],  # majority red
        102: [(0, "white", 20.0, 0.5), (1, "white", 20.0, 0.7)],  # white
        103: [(0, "red", 30.0, 0.4)],  # red (single observation)
    }
    result = _aggregate(obs)
    assert [lamp.index for lamp in result] == [1, 2, 3, 4]
    by_index = {lamp.index: lamp for lamp in result}

    # Lamp 1 (track 101): 2 red vs 1 white -> red; confidence averages the red frames.
    assert by_index[1].state == "red"
    assert by_index[1].confidence == 0.7
    # Lamp 2 (track 102): all white.
    assert by_index[2].state == "white"
    assert by_index[2].confidence == 0.6
    # Lamp 3 (track 103): single red observation.
    assert by_index[3].state == "red"
    assert by_index[3].confidence == 0.4
    # Lamp 4: never tracked -> obscured (detector found nothing at that slot).
    assert by_index[4].state == "obscured"
    assert by_index[4].confidence == 0.0


def test_aggregate_follows_track_identity_not_per_frame_rank():
    # The leftmost lamp wobbles in center_x frame-to-frame but keeps its track id;
    # the verdict must follow the track, never a per-frame rank that would scramble
    # when the centers jitter or a frame drops a lamp.
    obs = {
        201: [(0, "red", 10.0, 0.9), (1, "red", 9.0, 0.9), (2, "red", 11.0, 0.9)],  # leftmost, all red
        202: [(0, "white", 50.0, 0.9), (1, "white", 51.0, 0.9)],  # rightmost, all white
    }
    by_index = {lamp.index: lamp for lamp in _aggregate(obs)}
    assert by_index[1].state == "red"
    assert by_index[2].state == "white"
    assert by_index[3].state == "obscured"
    assert by_index[4].state == "obscured"


def test_aggregate_keeps_the_four_most_persistent_tracks():
    # A transient 1-frame false-positive track (999) must not displace a real lamp:
    # the four lamps seen across many frames win, ordered left-to-right.
    obs = {
        1: [(f, "red", 10.0, 0.9) for f in range(8)],
        2: [(f, "red", 20.0, 0.9) for f in range(8)],
        3: [(f, "white", 30.0, 0.9) for f in range(8)],
        4: [(f, "white", 40.0, 0.9) for f in range(8)],
        999: [(3, "white", 5.0, 0.95)],  # transient, leftmost center, high conf
    }
    states = [lamp.state for lamp in _aggregate(obs)]
    assert states == ["red", "red", "white", "white"]  # the persistent four, in order
