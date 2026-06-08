import numpy as np
from app.services.inference.detector import lamp_redness


def test_lamp_redness_high_for_red_low_for_white():
    # BGR frames: channel 2 is red. A red lamp dominates the red channel; a white
    # lamp has R~=G~=B, so its red FRACTION drops to ~1/3 of the scale.
    red = np.zeros((20, 20, 3), dtype=np.uint8)
    red[:, :, 2] = 240
    white = np.full((20, 20, 3), 230, dtype=np.uint8)

    r_red = lamp_redness(red, 0, 0, 20, 20)
    r_white = lamp_redness(white, 0, 0, 20, 20)

    assert r_red is not None and r_white is not None
    assert r_red > r_white  # red reads redder than white — the whole point
    assert r_red > 200  # pure red -> fraction ~255
    assert 70 < r_white < 100  # neutral grey/white -> ~85 (1/3 of 255)


def test_lamp_redness_none_for_non_image_or_empty():
    assert lamp_redness(None, 0, 0, 10, 10) is None
    assert lamp_redness("not-an-array.jpg", 0, 0, 10, 10) is None
    # Degenerate / out-of-bounds box -> None, never a crash.
    frame = np.full((10, 10, 3), 100, dtype=np.uint8)
    assert lamp_redness(frame, 5, 5, 5, 5) is None


def test_lamp_redness_clamps_out_of_bounds_box():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    frame[:, :, 2] = 200  # all red
    # Box extends past the frame; should clamp and still measure the red interior.
    assert lamp_redness(frame, -4, -4, 14, 14) is not None
