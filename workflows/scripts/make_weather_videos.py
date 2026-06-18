"""Render weather-degraded copies of a sample video, one clip per condition.

Produces synthetic rain/fog/haze/snow/sunflare/shadow versions of a clip so the demo and
manual testing can show the detector under adverse weather. Uses the same colour-safe transforms
as training (``weather_aug.apply_weather``), so what the model trains on matches what the demo
shows.

**Temporal coherence.** Applying an independent random draw per frame makes fog density and sun-
flare position flicker frame-to-frame. Each frame is rendered with a seeded
``numpy.random.default_rng`` (pure OpenCV/NumPy — no albumentations), so:

* STATIC conditions (fog, haze, sunflare, shadow) re-seed to the SAME value every frame → a
  frozen, settled overlay (no flicker).
* MOVING conditions (rain, snow) seed with ``seed + frame_index`` → streaks/flakes move naturally.

Both are fully reproducible from ``--seed``.

Output is VP8 ``.webm`` (browser-playable; the headless OpenCV wheel can't encode H.264 — see the
canonical ``apps/backend/app/services/inference/video_writer.py::open_video_writer``, whose
codec-fallback order this script mirrors). Files land in a gitignored ``output/`` dir by default.

Run::

    .venv/Scripts/python workflows/scripts/make_weather_videos.py \
        --input apps/frontend/public/demo-samples/papi24-angle-sweep.mp4 \
        --outdir output/weather-demos --conditions rain fog haze snow --severity medium --seed 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weather_aug import CONDITIONS, apply_weather  # noqa: E402

# Conditions whose overlay should stay PUT across frames (re-seed identically each frame).
_STATIC = {"fog", "haze", "sunflare", "shadow"}


def _open_writer(base_path: Path, fps: float, width: int, height: int):
    """Open a browser-playable video writer, mirroring the backend's codec-fallback order
    (avc1 .mp4 -> VP8 .webm -> mp4v .mp4). Returns (writer, path) or (None, None)."""
    for codec, ext in (("avc1", ".mp4"), ("VP80", ".webm"), ("mp4v", ".mp4")):
        path = base_path.with_suffix(ext)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*codec), fps, (width, height))
        if writer.isOpened():
            return writer, path
        writer.release()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return None, None


def _render(input_path: Path, condition: str, severity: str, seed: int, outdir: Path) -> dict:
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open input video: {input_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    base = outdir / f"{input_path.stem}-{condition}"
    writer, out_path = _open_writer(base, fps, width, height)
    if writer is None:
        cap.release()
        raise RuntimeError("no usable video codec (avc1/VP80/mp4v all failed to open a writer)")

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
        writer.release()
        cap.release()
    return {"condition": condition, "frames": n, "fps": round(fps, 3),
            "size": [width, height], "output": str(out_path)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="Source video (mp4/webm/...).")
    p.add_argument("--outdir", type=Path, default=Path("output/weather-demos"))
    p.add_argument("--conditions", nargs="+", default=["rain", "fog", "haze", "snow"],
                   choices=[c for c in CONDITIONS if c != "clear"])
    p.add_argument("--severity", default="medium", choices=["light", "medium", "heavy"])
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    if not args.input.is_file():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2
    args.outdir.mkdir(parents=True, exist_ok=True)

    results = [_render(args.input, c, args.severity, args.seed, args.outdir) for c in args.conditions]
    for r in results:
        print(f"  {r['condition']:9s} {r['frames']:4d} frames @ {r['fps']} fps -> {r['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
