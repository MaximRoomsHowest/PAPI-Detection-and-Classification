"""Frame-source plumbing: iterate a video capture and enforce the decode-size /
frame-count budgets. Pure helpers (settings are passed in, not read), so the
service keeps thin wrappers that supply ``self.settings`` and the tests can drive
the bounds directly."""

from typing import Any


def iter_video_frames(cap: Any):
    """Yield decoded BGR frames from an open ``cv2.VideoCapture``.

    Releasing the capture is the CALLER's job (``analyze_video`` does it in a
    ``finally``) so an early raise in the tracked-sequence core can't leak the handle.
    """
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        yield frame


def check_pixel_budget(width: int, height: int, max_megapixels: float, what: str = "image") -> None:
    """Reject a decoded frame whose pixel count exceeds the configured budget.

    The upload byte-cap does not bound decode amplification, so a small, highly
    compressed file can decode to gigabytes (a "decompression bomb"). Raising here
    (a ValueError -> HTTP 400) stops it before the frame is processed or copied. A
    non-positive dimension means "unknown" (e.g. cv2 CAP_PROP returned 0) and is left
    for the real decode to surface.
    """
    if width <= 0 or height <= 0:
        return
    max_pixels = max_megapixels * 1_000_000
    if width * height > max_pixels:
        raise ValueError(
            f"Uploaded {what} is too large to decode safely ({width}x{height} px); "
            f"the limit is {max_megapixels} megapixels."
        )


def video_frame_limit(fps: float, max_video_frames: int, max_video_seconds: float) -> int:
    frame_limit = max(1, max_video_frames)
    if max_video_seconds <= 0:
        return frame_limit
    seconds_limit = max(1, int(fps * max_video_seconds))
    return min(frame_limit, seconds_limit)
