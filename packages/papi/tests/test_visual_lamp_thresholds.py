"""Threshold-boundary tests for `papi.visual_lamp`'s named colour constants.

The existing ``test_visual_lamp.py`` exercises the full row-detection pipeline on
one synthetic image. This file complements it by pinning the *named constants*
(``_RED_MIN``, ``_RED_DOMINANCE``, ``_WHITE_*``, ``_STATE_MIN_PIXELS``,
``_TRANSITION_RATIO_*``, ``_RED_PIXEL_FRACTION``) directly at and around their
boundaries — so a future re-tune is a deliberate, test-visible change rather than
a silent regression. These are pure-function tests (no image decode needed).
"""

from __future__ import annotations

import numpy as np
from papi import visual_lamp as vl
from papi.visual_lamp import _Candidate, _lamp_masks


def _candidate(red_pixels: int, white_pixels: int, *, area: int = 50) -> _Candidate:
    """A candidate whose only state-relevant fields are the red/white pixel counts."""
    return _Candidate(
        cx=100.0,
        cy=100.0,
        x1=90,
        y1=90,
        x2=110,
        y2=112,
        area=area,
        red_pixels=red_pixels,
        white_pixels=white_pixels,
    )


# ---------------------------------------------------------------------------
# _Candidate.state — transition band (_STATE_MIN_PIXELS, _TRANSITION_RATIO_*)
# ---------------------------------------------------------------------------


def test_state_transition_requires_min_pixels_of_each_colour() -> None:
    """Both red and white counts must be >= _STATE_MIN_PIXELS for 'transition'."""
    n = vl._STATE_MIN_PIXELS  # 8
    # Exactly at the minimum on both, ratio 1.0 -> transition.
    assert _candidate(n, n).state == "transition"
    # One pixel short on white -> cannot be transition; falls through to red/white.
    assert _candidate(n, n - 1).state == "red"  # red >= max(8, .35*7) == 8
    # One pixel short on red -> not transition; red(7) < max(8, ...) -> white.
    assert _candidate(n - 1, n).state == "white"


def test_state_transition_ratio_band_inclusive_bounds() -> None:
    """ratio in [_TRANSITION_RATIO_LOW, _TRANSITION_RATIO_HIGH] reads as transition."""
    lo = vl._TRANSITION_RATIO_LOW  # 0.45
    hi = vl._TRANSITION_RATIO_HIGH  # 1.8
    white = 20
    # ratio exactly at the low bound (red/white == lo) -> transition (<=).
    assert _candidate(round(lo * white), white).state == "transition"  # 9/20 = 0.45
    # ratio exactly at the high bound -> transition.
    assert _candidate(round(hi * white), white).state == "transition"  # 36/20 = 1.8


def test_state_above_high_ratio_is_red_not_transition() -> None:
    """ratio just above _TRANSITION_RATIO_HIGH leaves the band -> classified 'red'."""
    white = 10
    red = int(vl._TRANSITION_RATIO_HIGH * white) + 5  # 23, ratio 2.3 > 1.8
    c = _candidate(red, white)
    assert c.state == "red"


def test_state_below_low_ratio_falls_through_to_red_fraction_rule() -> None:
    """ratio below _TRANSITION_RATIO_LOW is not transition; then the red-fraction rule decides."""
    # red/white == 0.2 (< 0.45): not transition. red(8) >= max(8, 0.35*40=14)? No -> white.
    assert _candidate(8, 40).state == "white"
    # red/white == 0.35 exactly the _RED_PIXEL_FRACTION: red(14) >= max(8, 14) -> red.
    assert _candidate(14, 40).state == "red"


def test_state_pure_red_blob_is_red() -> None:
    assert _candidate(8, 0).state == "red"  # red >= max(8, 0)
    # Just below the pixel floor with no white -> white (the catch-all).
    assert _candidate(vl._STATE_MIN_PIXELS - 1, 0).state == "white"


def test_state_no_pixels_defaults_to_white() -> None:
    assert _candidate(0, 0).state == "white"


# ---------------------------------------------------------------------------
# _lamp_masks — _RED_MIN, _RED_DOMINANCE, _WHITE_* boundaries
# ---------------------------------------------------------------------------


def _single_pixel(rgb: tuple[int, int, int]) -> tuple[bool, bool]:
    arr = np.array([[list(rgb)]], dtype=np.uint8)  # shape (1, 1, 3)
    red_mask, white_mask = _lamp_masks(arr)
    return bool(red_mask[0, 0]), bool(white_mask[0, 0])


def test_red_mask_requires_min_and_strict_dominance() -> None:
    # red channel must be strictly > _RED_MIN (150). 151 passes the floor.
    is_red, _ = _single_pixel((151, 90, 90))  # 151 > 90*1.45=130.5 -> red
    assert is_red
    # At/below the floor: 150 is NOT > 150 -> not red.
    assert _single_pixel((150, 10, 10)) == (False, False)
    # Bright red but green too high to dominate: 200 > 140*1.45=203 is False -> not red.
    assert _single_pixel((200, 140, 140))[0] is False
    # Bright red dominating green but not blue -> not red.
    assert _single_pixel((200, 100, 140))[0] is False  # 200 > 140*1.45=203 False


def test_white_mask_requires_all_channel_floors_and_low_spread() -> None:
    # All channels above their floors (190/160/110) and spread < 90 -> white.
    is_red, is_white = _single_pixel((200, 170, 120))  # spread 80 < 90
    assert is_white and not is_red
    # Blue one below its floor (109 < 110) -> not white.
    assert _single_pixel((200, 170, 109))[1] is False
    # Spread too large (255-150=105 >= 90) -> not white even though channels are bright.
    assert _single_pixel((255, 200, 150))[1] is False


def test_white_mask_floor_is_strict_greater_than() -> None:
    # Exactly on the red floor (190) fails the strict `>` for white.
    assert _single_pixel((190, 170, 120))[1] is False
    # One above the red floor, others clear, low spread -> white.
    assert _single_pixel((191, 170, 120))[1] is True


# ---------------------------------------------------------------------------
# _Candidate.padded_bbox — padding + image-edge clamping
# ---------------------------------------------------------------------------


def test_padded_bbox_clamps_to_image_bounds() -> None:
    """Padding never escapes [0, width-1] x [0, height-1]."""
    c = _Candidate(cx=5, cy=5, x1=0, y1=0, x2=10, y2=10, area=40, red_pixels=0, white_pixels=0)
    x1, y1, x2, y2 = c.padded_bbox(image_width=12, image_height=12)
    assert x1 == 0.0 and y1 == 0.0  # clamped at the low edge
    assert x2 <= 11.0 and y2 <= 11.0  # clamped at width-1 / height-1


def test_padded_bbox_minimum_pad_is_two_pixels() -> None:
    """A 1px-wide blob still gets the 2px minimum pad on each side."""
    c = _Candidate(cx=50, cy=50, x1=50, y1=50, x2=51, y2=51, area=1, red_pixels=0, white_pixels=0)
    x1, y1, x2, y2 = c.padded_bbox(image_width=200, image_height=200)
    assert x1 == 48.0 and y1 == 48.0  # 50 - 2
    assert x2 == 53.0 and y2 == 53.0  # 51 + 2
