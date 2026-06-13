from types import SimpleNamespace

import numpy as np
from app.services.inference.detector import detect_frame, lamp_redness


def test_lamp_redness_high_for_red_low_for_white():
    red_frame = np.zeros((20, 20, 3), dtype=np.uint8)
    red_frame[:, :, 2] = 255
    white_frame = np.full((20, 20, 3), 255, dtype=np.uint8)

    assert lamp_redness(red_frame, 0, 0, 20, 20) == 255.0
    assert lamp_redness(white_frame, 0, 0, 20, 20) == 85.0


def test_lamp_redness_none_for_non_image_or_empty():
    assert lamp_redness(object(), 0, 0, 10, 10) is None
    assert lamp_redness(np.zeros((10, 10, 3), dtype=np.uint8), 5, 5, 5, 6) is None
    assert lamp_redness(np.zeros((10, 10, 3), dtype=np.uint8), 20, 20, 30, 30) is None


def test_lamp_redness_clamps_out_of_bounds_box():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    frame[:, :, 1] = 255

    assert lamp_redness(frame, -5, -5, 20, 20) == 0.0


class _FakeBox:
    xyxy = [[1, 2, 3, 4]]
    cls = [0]
    conf = [0.9]
    id = [7]


class _FakeModel:
    def __init__(self):
        self.track_kwargs = None
        self.predict_kwargs = None

    def track(self, frame, **kwargs):
        self.track_kwargs = kwargs
        return [SimpleNamespace(boxes=[_FakeBox()])]

    def predict(self, frame, **kwargs):
        self.predict_kwargs = kwargs
        return [SimpleNamespace(boxes=[_FakeBox()])]


def test_detect_frame_caps_yolo_to_four_papi_lamps_for_tracking():
    model = _FakeModel()

    detections = detect_frame(
        model,
        object(),
        use_tracking=True,
        reset_tracker=True,
        conf=0.4,
        device="cpu",
    )

    assert model.track_kwargs["max_det"] == 4
    assert detections[0]["track_id"] == 7


def test_detect_frame_caps_yolo_to_four_papi_lamps_for_predict():
    model = _FakeModel()

    detect_frame(
        model,
        object(),
        use_tracking=False,
        reset_tracker=False,
        conf=0.4,
        device="cpu",
    )

    assert model.predict_kwargs["max_det"] == 4
