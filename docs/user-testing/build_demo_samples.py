#!/usr/bin/env python3
"""Regenerate the Live-Demo sample-picker assets in apps/frontend/public/demo-samples/.

Single source of truth for WHERE the demo samples come from: the real EDNY
rwy-24 day clip ``DJI_202604291738_041_300mday2up`` in the git-ignored
``data/datasets/transition-classification-data/`` (162 frames, drone climbing
through every PAPI set angle at ~300 m stand-off; per-frame RTK fixes in the
clip's ``metadata.csv``). Frames are ordered by ``sequence_index`` and every
telemetry fix is the one recorded WITH its frame, so the displayed angle always
agrees with what the lamps show.

Same detection-critical rule as build_media.py: downscale the FULL frame to a
1280 px long edge, never crop (a PAPI-centred crop blows the lamps out of the
training distribution and the detector finds nothing).

Outputs:
  papi-test-frame.jpg + sample-point.json     on-slope single frame + its own fix
  folder-frame-001..010.jpg + sample-sweep.json   10-frame sweep (30%..97% span)
  papi24-angle-sweep.mp4 + sample-video.json      ~2-minute clip: 120 evenly
      picked frames over the WHOLE climb at 1 fps (H.264 yuv420p faststart —
      browser-playable AND OpenCV-decodable), with a 1:1 120-fix telemetry file.
      NOTE: needs PAPI_MAX_VIDEO_SECONDS >= 120 (default raised to 150).

Run from the repo root (uses the repo .venv: PIL + imageio-ffmpeg):
    .venv/Scripts/python.exe docs/user-testing/build_demo_samples.py
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CLIP = REPO / "data" / "datasets" / "transition-classification-data" / "daytime" / "DJI_202604291738_041_300mday2up"
OUT = REPO / "apps" / "frontend" / "public" / "demo-samples"
LONG_EDGE = 1280
# 60 real frames at 0.5 fps -> exactly 2 minutes. Half-fps over more unique
# frames was 15 MB; this keeps the same climb at ~7 MB and ~half the
# inference time (~30 s on the demo CPU) while every frame stays real.
VIDEO_FRAMES = 60
VIDEO_FPS = 0.5


def load_rows() -> list[dict]:
    rows = list(csv.DictReader(open(CLIP / "metadata.csv", newline="", encoding="utf-8")))
    rows.sort(key=lambda r: int(r["sequence_index"]))
    return rows


def pick(rows: list[dict], n: int, lo: float, hi: float) -> list[dict]:
    """n rows evenly spread over the [lo, hi] fraction of the clip, in order."""
    a, b = int(len(rows) * lo), int(len(rows) * hi) - 1
    if n == 1:
        return [rows[(a + b) // 2]]
    return [rows[a + round(i * (b - a) / (n - 1))] for i in range(n)]


def emit_frame(row: dict, dst: Path) -> None:
    from PIL import Image

    img = Image.open(CLIP / row["image"]).convert("RGB")
    w, h = img.size
    s = LONG_EDGE / max(w, h)
    if s < 1:
        img = img.resize((round(w * s), round(h * s)), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, "JPEG", quality=88)


def fixes(rows: list[dict]) -> list[dict]:
    return [
        {
            "frame_index": i,
            "latitude": round(float(r["lat"]), 8),
            "longitude": round(float(r["lon"]), 8),
            "altitude_m": round(float(r["alt_ellipsoidal_m"]), 3),
        }
        for i, r in enumerate(rows)
    ]


def write_track(path: Path, rows: list[dict], note: str) -> None:
    path.write_text(
        json.dumps({"runway": "papi_24", "note": note, "samples": fixes(rows)}, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    if not (CLIP / "metadata.csv").exists():
        print(f"Dataset clip not found: {CLIP}", file=sys.stderr)
        return 1
    rows = load_rows()
    OUT.mkdir(parents=True, exist_ok=True)

    # --- 10-frame sweep folder + matching telemetry (same recipe as build_media.py)
    sweep = pick(rows, 10, 0.30, 0.97)
    for i, r in enumerate(sweep, 1):
        emit_frame(r, OUT / f"folder-frame-{i:03d}.jpg")
    write_track(
        OUT / "sample-sweep.json",
        sweep,
        "Real per-frame drone fixes for sweep_papi24_300m_day (EDNY papi_24).",
    )

    # --- on-slope single frame (sweep index 4, ~2.8 deg) + its own point fix
    single = sweep[4]
    emit_frame(single, OUT / "papi-test-frame.jpg")
    (OUT / "sample-point.json").write_text(
        json.dumps(
            {
                "runway": "papi_24",
                "note": "Real drone fix matching papi-test-frame.jpg (sweep frame 5, on-slope).",
                "latitude": round(float(single["lat"]), 8),
                "longitude": round(float(single["lon"]), 8),
                "altitude_m": round(float(single["alt_ellipsoidal_m"]), 3),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # --- ~2-minute video over the WHOLE climb + 1:1 telemetry
    video_rows = pick(rows, VIDEO_FRAMES, 0.0, 1.0)
    import imageio_ffmpeg

    with tempfile.TemporaryDirectory() as tmp:
        for i, r in enumerate(video_rows, 1):
            emit_frame(r, Path(tmp) / f"v{i:04d}.jpg")
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-framerate", str(VIDEO_FPS),
                "-i", str(Path(tmp) / "v%04d.jpg"),
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-c:v", "libx264",
                "-preset", "slow",
                "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(OUT / "papi24-angle-sweep.mp4"),
            ],
            check=True,
            capture_output=True,
        )
    write_track(
        OUT / "sample-video.json",
        video_rows,
        "Real per-frame drone fixes for papi24-angle-sweep.mp4 (1 fix per video frame).",
    )

    size_mb = (OUT / "papi24-angle-sweep.mp4").stat().st_size / 1e6
    alts = [float(r["alt_ellipsoidal_m"]) for r in video_rows]
    print(f"video: {VIDEO_FRAMES} frames @ {VIDEO_FPS} fps = {int(VIDEO_FRAMES / VIDEO_FPS)}s, "
          f"{size_mb:.1f} MB, alt {alts[0]:.1f} -> {alts[-1]:.1f} m")
    print(f"sweep: 10 frames, single: seq {single['sequence_index']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
