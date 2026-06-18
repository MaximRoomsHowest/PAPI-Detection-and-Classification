"""Render weather-degraded copies of a sample video, one clip per condition.

Produces synthetic rain/fog/haze/snow/sunflare/shadow versions of a clip so the demo and
manual testing can show the detector under adverse weather. Uses the same colour-safe transforms
as training (``weather_aug.apply_weather``), so what the model trains on matches what the demo
shows.

**Temporal coherence.** Applying an independent random draw per frame makes fog density and sun-
flare position flicker frame-to-frame. Each frame is rendered with a seeded
``numpy.random.default_rng`` (pure OpenCV/NumPy - no albumentations), so:

* STATIC conditions (fog, haze, sunflare, shadow) re-seed to the SAME value every frame -> a
  frozen, settled overlay (no flicker).
* MOVING conditions (rain, snow) seed with ``seed + frame_index`` -> streaks/flakes move naturally.

Both are fully reproducible from ``--seed``.

Output is H.264 ``.mp4`` (``yuv420p`` + ``+faststart``), encoded by piping frames to an ffmpeg
binary - the system ``ffmpeg`` if present, otherwise the one ``imageio-ffmpeg`` bundles. This is
both browser-playable and decodable by the backend's OpenCV/FFMPEG reader. When no ffmpeg is
available (``--no-ffmpeg`` or neither found) it falls back to the OpenCV codec chain
(avc1 .mp4 -> VP8 .webm -> mp4v .mp4), mirroring
``apps/backend/app/services/inference/video_writer.py::open_video_writer``. Files land in a
gitignored ``output/`` dir by default.

Run::

    .venv/Scripts/python workflows/scripts/make_weather_videos.py \
        --input apps/frontend/public/demo-samples/papi24-angle-sweep.mp4 \
        --outdir output/weather-demos --conditions rain fog haze snow --severity medium --seed 0
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weather_aug import CONDITIONS, apply_weather  # noqa: E402

# Conditions whose overlay should stay PUT across frames (re-seed identically each frame).
_STATIC = {"fog", "haze", "sunflare", "shadow"}


def _resolve_ffmpeg() -> str | None:
    """Locate an ffmpeg binary: system PATH first, then the one ``imageio-ffmpeg`` bundles.

    Returns ``None`` when neither is available (callers fall back to the OpenCV writer)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # optional; only used as an ffmpeg provider

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - any import/lookup failure means "no ffmpeg", fall back
        return None


class _FfmpegWriter:
    """Pipe BGR uint8 frames to ffmpeg -> a browser- AND backend-decodable H.264 mp4.

    ``yuv420p`` + ``+faststart`` so every browser and the backend's OpenCV/FFMPEG decoder both
    play the clip; the ``pad`` filter rounds odd dimensions up to even (H.264 4:2:0 requires it).
    This is the canonical demo encoder - it sidesteps the OpenCV Windows wheel's flaky avc1
    (needs an external OpenH264 DLL) and webm muxer. The OpenCV chain (`_open_cv_writer`) is the
    no-ffmpeg fallback only."""

    def __init__(self, exe: str, path: Path, fps: float, width: int, height: int, crf: int):
        self.path = path
        self._proc = subprocess.Popen(
            [exe, "-y", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
             "-r", f"{fps}", "-i", "-",
             "-an", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
             "-crf", str(crf), "-movflags", "+faststart", str(path)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

    def write(self, frame_bgr: np.ndarray) -> None:
        self._proc.stdin.write(np.ascontiguousarray(frame_bgr, dtype=np.uint8).tobytes())

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        err = self._proc.stderr.read() if self._proc.stderr else b""
        rc = self._proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg encode failed (rc={rc}): {err.decode('utf-8', 'replace')[:800]}")


class _CvWriter:
    """Adapter giving ``cv2.VideoWriter`` the same ``write``/``close``/``path`` shape."""

    def __init__(self, writer: cv2.VideoWriter, path: Path):
        self._w = writer
        self.path = path

    def write(self, frame_bgr: np.ndarray) -> None:
        self._w.write(frame_bgr)

    def close(self) -> None:
        self._w.release()


def _open_cv_writer(base_path: Path, fps: float, width: int, height: int):
    """No-ffmpeg fallback: mirror the backend's codec-fallback order (avc1 .mp4 -> VP8 .webm ->
    mp4v .mp4). Returns a `_CvWriter` or ``None`` when every codec fails to open."""
    for codec, ext in (("avc1", ".mp4"), ("VP80", ".webm"), ("mp4v", ".mp4")):
        path = base_path.with_suffix(ext)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, (width, height))
        if writer.isOpened():
            return _CvWriter(writer, path)
        writer.release()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return None


def _make_writer(base_path: Path, fps: float, width: int, height: int,
                 ffmpeg_exe: str | None, crf: int):
    """Prefer the ffmpeg H.264 writer (clean, portable .mp4); fall back to OpenCV codecs."""
    if ffmpeg_exe:
        return _FfmpegWriter(ffmpeg_exe, base_path.with_suffix(".mp4"), fps, width, height, crf)
    writer = _open_cv_writer(base_path, fps, width, height)
    if writer is None:
        raise RuntimeError(
            "no usable video codec: install ffmpeg (or `pip install imageio-ffmpeg`), "
            "or fix the OpenCV avc1/VP80/mp4v writers")
    return writer


def _render(input_path: Path, condition: str, severity: str, seed: int, outdir: Path,
            ffmpeg_exe: str | None, crf: int) -> dict:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open input video: {input_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    base = outdir / f"{input_path.stem}-{condition}"
    writer = _make_writer(base, fps, width, height, ffmpeg_exe, crf)

    static = condition in _STATIC
    n = 0
    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            # Temporal coherence: STATIC conditions reseed identically each frame (frozen overlay);
            # MOVING conditions advance the seed by frame index (streaks/flakes move). Reproducible.
            rng = np.random.default_rng(seed if static else seed + n)
            writer.write(apply_weather(frame_bgr, condition, severity, rng))
            n += 1
    finally:
        writer.close()
        cap.release()
    return {"condition": condition, "frames": n, "fps": round(fps, 3),
            "size": [width, height], "output": str(writer.path)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="Source video (mp4/webm/...).")
    p.add_argument("--outdir", type=Path, default=Path("output/weather-demos"))
    p.add_argument("--conditions", nargs="+", default=["rain", "fog", "haze", "snow"],
                   choices=[c for c in CONDITIONS if c != "clear"])
    p.add_argument("--severity", default="medium", choices=["light", "medium", "heavy"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--crf", type=int, default=26,
                   help="H.264 quality for the ffmpeg encoder (lower = better/larger). Default 26.")
    p.add_argument("--no-ffmpeg", action="store_true",
                   help="Force the OpenCV codec fallback instead of the ffmpeg H.264 writer.")
    args = p.parse_args()

    if not args.input.is_file():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2
    args.outdir.mkdir(parents=True, exist_ok=True)

    ffmpeg_exe = None if args.no_ffmpeg else _resolve_ffmpeg()
    print(f"encoder: {'ffmpeg H.264 (' + ffmpeg_exe + ')' if ffmpeg_exe else 'OpenCV fallback'}")
    results = [_render(args.input, c, args.severity, args.seed, args.outdir, ffmpeg_exe, args.crf)
               for c in args.conditions]
    for r in results:
        print(f"  {r['condition']:9s} {r['frames']:4d} frames @ {r['fps']} fps -> {r['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
