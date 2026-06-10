"""Mid-stream truncation contract of the tracked-sequence core (audit B2).

A source that out-runs max_frames mid-loop (container metadata lied or was absent)
previously raised after paying for max_frames worth of inference, discarding the
artifact. It must instead keep the processed prefix and say so on the payload.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest
from app.services.inference.sequence_runner import run_tracked_sequence
from app.validation.schemas import AngleResult


def _detect(frame, *, use_tracking, reset_tracker=False):
    return [
        {
            "class_id": 0,
            "track_id": 1,
            "confidence": 0.9,
            "bbox": {"x1": 1.0, "y1": 1.0, "x2": 3.0, "y2": 3.0},
        }
    ]


def _run(frame_iter, *, max_frames, tmp_path):
    return run_tracked_sequence(
        frame_iter,
        detect=_detect,
        cv2=MagicMock(),  # writer/overlay calls are irrelevant to the truncation contract
        fps=15.0,
        width=8,
        height=8,
        runway_id="papi_24",
        original_filename="long.mp4",
        drone_id=None,
        angle=AngleResult(angle_available=False, angle_note="test: no metadata"),
        start=0.0,
        max_frames=max_frames,
        empty_message="empty",
        history_size=5,
        exports_dir=tmp_path,
    )


def test_sequence_truncates_at_max_frames_and_signals_it(tmp_path):
    frames = (np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(10))

    payload = _run(frames, max_frames=4, tmp_path=tmp_path)

    assert payload.frame_count == 4
    assert payload.truncated_at_frame == 4
    assert payload.artifact_url is not None  # the processed prefix is kept


def test_sequence_within_limit_is_not_marked_truncated(tmp_path):
    frames = (np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(3))

    payload = _run(frames, max_frames=4, tmp_path=tmp_path)

    assert payload.frame_count == 3
    assert payload.truncated_at_frame is None


def test_empty_stream_still_raises(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        _run(iter(()), max_frames=4, tmp_path=tmp_path)
