import math

from papi.transition_labels import Flip, empirical_set_angle, parse_flips, window_frames


def test_parse_flips_builds_records():
    rows = [
        {
            "track_id": "t1",
            "physical_lamp_id": "lamp_2",
            "from_frame_index": "10",
            "to_frame_index": "11",
            "from_state": "red",
            "to_state": "white",
            "transition_type": "red_to_white",
        }
    ]
    flips = parse_flips(rows)
    assert len(flips) == 1
    flip = flips[0]
    assert flip.track_id == "t1"
    assert flip.lamp_position == "lamp_2"
    assert flip.from_frame == 10 and flip.to_frame == 11
    assert flip.transition_type == "red_to_white"


def test_parse_flips_missing_lamp_id_defaults_to_empty():
    rows = [
        {
            "track_id": "t1",
            "from_frame_index": "5",
            "to_frame_index": "6",
            "from_state": "white",
            "to_state": "red",
            "transition_type": "white_to_red",
        }
    ]
    assert parse_flips(rows)[0].lamp_position == ""


def _flip(from_frame: int, to_frame: int) -> Flip:
    return Flip(
        track_id="t",
        lamp_position="lamp_1",
        from_frame=from_frame,
        to_frame=to_frame,
        from_state="red",
        to_state="white",
        transition_type="red_to_white",
    )


def test_window_frames_bounds_to_observed_frames():
    observed = {5, 8, 9, 10, 11, 12, 13, 20}
    flip = _flip(10, 11)
    # half_window=2 -> lo = 10-2+1 = 9, hi = 11+2-1 = 12
    assert window_frames(flip, half_window=2, observed=observed) == [9, 10, 11, 12]
    # half_window=1 -> lo = 10, hi = 11 (just the flip boundary)
    assert window_frames(flip, half_window=1, observed=observed) == [10, 11]
    # An observed set that misses the window yields nothing.
    assert window_frames(flip, half_window=1, observed={1, 2, 3}) == []


def test_empirical_set_angle_is_median_with_nan_and_none_filtered():
    assert empirical_set_angle([2.0]) == 2.0
    assert empirical_set_angle([2.0, 3.0, 4.0]) == 3.0
    assert empirical_set_angle([math.nan, 2.0, 4.0]) == 3.0  # NaN dropped before the median
    assert empirical_set_angle([None, 2.0]) == 2.0  # None dropped
    assert empirical_set_angle([]) is None
    assert empirical_set_angle([math.nan]) is None
