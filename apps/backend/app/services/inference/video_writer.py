"""Annotated-video writer with browser-playable codec selection."""

from pathlib import Path
from typing import Any


def open_video_writer(
    cv2: Any, base_path: Path, fps: float, width: int, height: int
) -> tuple[Any, Path] | tuple[None, None]:
    """Open an annotated-video writer with a BROWSER-PLAYABLE codec, returning
    (writer, path) with the file extension matched to the chosen codec
    (audit IMP-SRV-6 / video-annotation-unplayable).

    Order of preference:
      1. avc1 (H.264, .mp4) — ideal, but the headless opencv-python wheel ships
         no H.264 *encoder* (licensing), so this opens only where one is present.
      2. VP8 (.webm) — the headless build CAN encode this and every modern
         browser plays it, so it is the working default in the Docker image.
      3. mp4v (MPEG-4 Part 2, .mp4) — last resort: opens almost everywhere but
         most browsers refuse to play it ("Unable to play media").
    Returns (None, None) if no codec opens a writer.
    """
    for codec, ext in (("avc1", ".mp4"), ("VP80", ".webm"), ("mp4v", ".mp4")):
        path = base_path.with_suffix(ext)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, (width, height))
        if writer.isOpened():
            return writer, path
        writer.release()
    return None, None
