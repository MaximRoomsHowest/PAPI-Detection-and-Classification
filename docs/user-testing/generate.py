#!/usr/bin/env python3
"""Generate the HEAVY / EDGE user-test inputs that are too large or too synthetic to
commit. Everything this writes lands under ``docs/user-testing/`` in git-ignored
folders (see ``.gitignore``), so the repo stays lean while a tester can recreate the
full adversarial set in one command.

Run from the repo root (uses the repo .venv which already has cv2 / PIL / numpy):

    .venv/Scripts/python.exe docs/user-testing/generate.py            # all artifacts
    .venv/Scripts/python.exe docs/user-testing/generate.py --only edge

What it produces (each maps to a row in test-plan.md):
  media/single-image/geotagged_papi24.jpg   real frame + EXIF GPS  -> angle "from image GPS"
  media/edge/huge_pixels_81mp.png           9000x9000 (>80 MP)     -> 400 pixel-cap
  media/edge/oversized_105mb.jpg            >100 MB valid JPEG     -> frontend size reject / 413
  media/edge/wrong_signature.jpg            PNG bytes, .jpg name   -> 400 signature mismatch
  media/edge/corrupt_truncated.jpg          half a JPEG            -> 400 / decode error
  media/edge/zero_byte.jpg                   0 bytes               -> empty-file reject
  media/edge/not_a_video.mp4                JPEG bytes, .mp4 name  -> 400 signature mismatch
  media/image-batch/oversized_batch_201/    201 images            -> frontend "too many images"
  media/image-batch/mixed_types/            images + 1 .txt       -> non-image dropped by accept=
  media/image-batch/sequence_papi06_night/  real night frames     -> richer papi_06 sequence
  media/video/over_600frames.mp4            >600 frames           -> video frame cap applied

Constructed telemetry/positions are ILLUSTRATIVE test input near EDNY, not surveyed truth.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TEST_VIDEOS = REPO / "test_videos"
QA_FRAMES = REPO / "docs" / "qa-artifacts" / "frames"

# EDNY papi_24 PAPI cluster (~47.6735 N, 9.5181 E, 461.37 m WGS-84); a fix ~700 m north
# and ~60 m above the lamps gives a realistic few-degree approach angle.
GEO_LAT, GEO_LON, GEO_ALT = 47.679800, 9.518100, 520.0


def _src_frame() -> Path:
    for cand in (
        QA_FRAMES / "daytime_DJI_202604291738_041_300mday2up_smoke_frame001.jpg",
        TEST_VIDEOS / "_test_frame.jpg",
        TEST_VIDEOS / "_folder_test" / "frame_001.jpg",
    ):
        if cand.exists():
            return cand
    raise SystemExit("No source frame found under test_videos/ or docs/qa-artifacts/frames/.")


def _src_video(night: bool = False) -> Path:
    name = (
        "nighttime_DJI_202604290007_019_300mRwy06night_smoke.mp4"
        if night
        else "daytime_DJI_202604291738_041_300mday2up_smoke.mp4"
    )
    p = TEST_VIDEOS / name
    if not p.exists():
        raise SystemExit(f"Source video missing: {p}")
    return p


def gen_geotagged(out_dir: Path) -> None:
    """Real PAPI frame stamped with EXIF GPS so the backend computes an angle
    'from image GPS' with no telemetry file. Needs piexif (``pip install piexif``);
    Pillow's native Exif writer can't serialise a GPS IFD reliably, so this is the
    one optional dependency — skipped (non-fatal) if piexif is absent."""
    try:
        import piexif
    except ImportError:
        print("  geotagged_papi24.jpg  SKIPPED (optional: pip install piexif)")
        return
    from PIL import Image

    def _dms(value: float):
        value = abs(value)
        deg = int(value)
        minutes = int((value - deg) * 60)
        seconds = round((value - deg - minutes / 60) * 3600, 4)
        return ((deg, 1), (minutes, 1), (int(seconds * 10000), 10000))

    gps_ifd = {
        piexif.GPSIFD.GPSVersionID: (2, 3, 0, 0),
        piexif.GPSIFD.GPSLatitudeRef: "N" if GEO_LAT >= 0 else "S",
        piexif.GPSIFD.GPSLatitude: _dms(GEO_LAT),
        piexif.GPSIFD.GPSLongitudeRef: "E" if GEO_LON >= 0 else "W",
        piexif.GPSIFD.GPSLongitude: _dms(GEO_LON),
        piexif.GPSIFD.GPSAltitudeRef: 0,
        piexif.GPSIFD.GPSAltitude: (int(GEO_ALT * 1000), 1000),
    }
    exif_bytes = piexif.dump({"GPS": gps_ifd})
    out = out_dir / "geotagged_papi24.jpg"
    Image.open(_src_frame()).convert("RGB").save(out, "JPEG", exif=exif_bytes, quality=92)
    print(f"  geotagged_papi24.jpg  ({out.stat().st_size // 1024} KB, GPS {GEO_LAT},{GEO_LON},{GEO_ALT})")


def gen_edge(out_dir: Path) -> None:
    from PIL import Image

    out_dir.mkdir(parents=True, exist_ok=True)
    frame_bytes = _src_frame().read_bytes()

    # 9000x9000 = 81 MP > the 80 MP decompression-bomb cap.
    Image.new("RGB", (9000, 9000), (40, 40, 48)).save(out_dir / "huge_pixels_81mp.png")
    print("  huge_pixels_81mp.png  (81 MP -> pixel cap)")

    # >100 MB valid JPEG: real JPEG bytes then zero padding after EOI (signature intact).
    big = out_dir / "oversized_105mb.jpg"
    with open(big, "wb") as fh:
        fh.write(frame_bytes)
        fh.write(b"\x00" * (105 * 1024 * 1024 - len(frame_bytes)))
    print(f"  oversized_105mb.jpg   ({big.stat().st_size // (1024 * 1024)} MB -> size limit)")

    # PNG magic bytes but a .jpg name -> signature/extension mismatch.
    png = out_dir / "wrong_signature.jpg"
    Image.new("RGB", (320, 240), (90, 20, 20)).save(png.with_suffix(".png"))
    shutil.move(str(png.with_suffix(".png")), str(png))
    print("  wrong_signature.jpg   (PNG bytes, .jpg name -> 400 signature)")

    # Truncated JPEG: keep the SOI + first half, drop the rest.
    (out_dir / "corrupt_truncated.jpg").write_bytes(frame_bytes[: len(frame_bytes) // 2])
    print("  corrupt_truncated.jpg (half a JPEG -> decode error)")

    (out_dir / "zero_byte.jpg").write_bytes(b"")
    print("  zero_byte.jpg         (0 bytes)")

    (out_dir / "not_a_video.mp4").write_bytes(frame_bytes)
    print("  not_a_video.mp4       (JPEG bytes, .mp4 name -> 400 signature)")


def gen_batches(out_dir: Path) -> None:
    frame = _src_frame()

    # 201 images > the 200-frame folder cap (frontend rejects before any upload).
    big = out_dir / "oversized_batch_201"
    big.mkdir(parents=True, exist_ok=True)
    for i in range(1, 202):
        shutil.copy(frame, big / f"frame_{i:03d}.jpg")
    print("  oversized_batch_201/  (201 images -> 'too many images')")

    # Two valid images + one non-image; the <input accept='image/*'> drops the .txt.
    mixed = out_dir / "mixed_types"
    mixed.mkdir(parents=True, exist_ok=True)
    shutil.copy(frame, mixed / "frame_001.jpg")
    shutil.copy(frame, mixed / "frame_002.jpg")
    (mixed / "notes.txt").write_text("not an image\n", encoding="utf-8")
    print("  mixed_types/          (2 images + notes.txt)")


def gen_night_sequence(out_dir: Path, n: int = 8) -> None:
    import cv2

    seq = out_dir / "sequence_papi06_night"
    seq.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(_src_video(night=True)))
    saved = 0
    while saved < n:
        ok, frame = cap.read()
        if not ok:
            break
        cv2.imwrite(str(seq / f"frame_{saved + 1:03d}.jpg"), frame)
        saved += 1
    cap.release()
    print(f"  sequence_papi06_night/ ({saved} real night frames)")


def gen_long_video(out_dir: Path, target_frames: int = 720) -> None:
    """Loop a real clip to >600 frames so the video frame cap is exercised."""
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    src = _src_video()
    cap = cv2.VideoCapture(str(src))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    if not frames:
        print("  over_600frames.mp4    SKIPPED (could not read source frames)")
        return
    h, w = frames[0].shape[:2]
    out = out_dir / "over_600frames.mp4"
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (w, h))
    for i in range(target_frames):
        writer.write(frames[i % len(frames)])
    writer.release()
    print(f"  over_600frames.mp4    ({target_frames} frames @30fps -> frame cap)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--only",
        choices=["geotagged", "edge", "batches", "night", "video", "all"],
        default="all",
    )
    args = ap.parse_args()
    sel = args.only

    media = HERE / "media"
    print("Generating user-test edge inputs (git-ignored) under docs/user-testing/media/ ...")
    steps = [
        ("geotagged", lambda: gen_geotagged(media / "single-image")),
        ("edge", lambda: gen_edge(media / "edge")),
        ("batches", lambda: gen_batches(media / "image-batch")),
        ("night", lambda: gen_night_sequence(media / "image-batch")),
        ("video", lambda: gen_long_video(media / "video")),
    ]
    failures = 0
    for name, fn in steps:
        if sel not in (name, "all"):
            continue
        try:
            fn()
        except Exception as exc:  # one bad step shouldn't abort the rest
            failures += 1
            print(f"  [{name}] SKIPPED: {type(exc).__name__}: {exc}")
    print("Done." if not failures else f"Done with {failures} skipped step(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
