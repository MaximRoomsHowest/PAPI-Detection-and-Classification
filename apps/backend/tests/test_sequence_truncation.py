"""Partial-source contracts of the tracked-sequence core.

Two opposite failure shapes must both be SAID on the payload, not silently
normalised:
- truncation (audit B2): the source out-ran max_frames mid-loop — keep the
  processed prefix, stamp ``truncated_at_frame``.
- decode shortfall (audit 2026-06-12): the source ended EARLY (a mid-stream
  decode error reads like EOF; unreadable sequence images are skipped) — stamp
  ``decode_shortfall`` when the gap exceeds the caller's tolerance.
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


def _run(frame_iter, *, max_frames, tmp_path, cv2=None, expected=None, tolerance=0):
    return run_tracked_sequence(
        frame_iter,
        detect=_detect,
        # writer/overlay calls are irrelevant to the truncation contract; pass a
        # shared mock in to assert WHICH frames were written before the cut.
        cv2=cv2 if cv2 is not None else MagicMock(),
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
        exports_dir=tmp_path,
        expected_frame_count=expected,
        shortfall_tolerance=tolerance,
    )


def test_sequence_truncates_at_max_frames_and_signals_it(tmp_path):
    frames = (np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(10))
    fake_cv2 = MagicMock()

    payload = _run(frames, max_frames=4, tmp_path=tmp_path, cv2=fake_cv2)

    assert payload.frame_count == 4
    assert payload.truncated_at_frame == 4
    assert payload.artifact_url is not None  # the processed prefix is kept
    # The "kept prefix" is real, not just a field: exactly the 4 pre-cut frames
    # were handed to the video writer, and the writer was finalized (release),
    # so the artifact on disk contains the prefix rather than being abandoned.
    writer = fake_cv2.VideoWriter.return_value
    assert writer.write.call_count == 4
    assert writer.release.called


def test_sequence_within_limit_is_not_marked_truncated(tmp_path):
    frames = (np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(3))

    payload = _run(frames, max_frames=4, tmp_path=tmp_path)

    assert payload.frame_count == 3
    assert payload.truncated_at_frame is None


def test_empty_stream_still_raises(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        _run(iter(()), max_frames=4, tmp_path=tmp_path)


# --- decode shortfall (the opposite of truncation) -------------------------


def _frames(n):
    return (np.zeros((8, 8, 3), dtype=np.uint8) for _ in range(n))


def test_shortfall_is_stamped_when_source_ends_early(tmp_path):
    """200 promised, 120 decoded (a mid-stream decode failure looks like EOF):
    the payload must say 80 frames went missing, not present as complete."""
    payload = _run(_frames(120), max_frames=500, tmp_path=tmp_path, expected=200, tolerance=10)

    assert payload.frame_count == 120
    assert payload.decode_shortfall == 80
    assert payload.truncated_at_frame is None


def test_shortfall_within_tolerance_is_not_reported(tmp_path):
    """Video container counts are approximate — a couple of frames short is
    metadata noise, not corruption."""
    payload = _run(_frames(98), max_frames=500, tmp_path=tmp_path, expected=100, tolerance=2)

    assert payload.decode_shortfall is None


def test_exact_source_one_missing_frame_is_reported_at_zero_tolerance(tmp_path):
    """Image sequences promise an exact file count: a single unreadable
    (skipped) image is a real shortfall."""
    payload = _run(_frames(9), max_frames=500, tmp_path=tmp_path, expected=10, tolerance=0)

    assert payload.decode_shortfall == 1


def test_complete_source_has_no_shortfall(tmp_path):
    payload = _run(_frames(10), max_frames=500, tmp_path=tmp_path, expected=10, tolerance=0)

    assert payload.decode_shortfall is None


def test_cap_truncation_does_not_double_report_as_shortfall(tmp_path):
    """A run cut by max_frames inevitably processes fewer frames than promised;
    that is the truncation contract's story, not a decode failure."""
    payload = _run(_frames(10), max_frames=4, tmp_path=tmp_path, expected=10, tolerance=0)

    assert payload.truncated_at_frame == 4
    assert payload.decode_shortfall is None


def test_no_expected_count_means_no_shortfall_check(tmp_path):
    """Containers without a frame-count header (expected=None) can't be judged."""
    payload = _run(_frames(5), max_frames=500, tmp_path=tmp_path, expected=None)

    assert payload.decode_shortfall is None
