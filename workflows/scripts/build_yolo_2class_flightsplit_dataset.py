"""Build a leak-free 2-class (red/white) YOLO detection dataset for the Small detector.

The current serving detector (``yolo26s-fulldata-1280``) was trained on a *random
per-frame* split (``PAPI_Split``) — adjacent near-identical frames leaked across
train/test, inflating its reported numbers (MODELS.md §3.1.2/§6). This builder fixes
that: it assigns whole FLIGHTS to train/val/test from ``configs/split.yaml`` so no
flight straddles the split, and strips the 3-class ``transition`` boxes (class 2) so the
labels match a pure red/white detector.

Fast-decode by design: source frames are ~20 MP, and decoding them every epoch is the
training bottleneck (not the GPU). By default images are downscaled once to longest-edge
``--max-side`` (1536 px) and saved as q95 JPEG — YOLO downscales to imgsz=1280 each epoch
anyway, so training detail is identical but per-epoch decode is ~10x faster (≈1 GB total
on disk). Pass ``--max-side 0`` to instead hard-link the originals at full resolution
(same NTFS volume → one inode, ~0 extra bytes; falls back to copy cross-volume).
Normalized YOLO boxes are scale-invariant, so resizing never touches the labels.

Run::

    .venv/Scripts/python workflows/scripts/build_yolo_2class_flightsplit_dataset.py
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
DEFAULT_SPLIT = REPO_ROOT / "configs" / "split.yaml"
DEFAULT_OUT = REPO_ROOT / "data" / "datasets" / "papi-2class-detection-flightsplit"
SOURCE_GROUPS = ("daytime", "nighttime")
CLASS_NAMES = {0: "papi_light_red", 1: "papi_light_white"}
IMG_EXTS = (".jpg", ".jpeg", ".png")


def _filter_label(text: str) -> str:
    """Drop class-2 (transition) boxes; keep red (0) / white (1) lines verbatim."""
    kept = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "2":  # transition — invalid for a binary red/white detector
            continue
        kept.append(line)
    return ("\n".join(kept) + "\n") if kept else ""


def _place_image(src: Path, dst: Path, max_side: int) -> None:
    """Put the training image at dst.

    With ``max_side > 0`` the image is decoded once and downscaled so its longest edge
    is ``max_side`` (never upscaled), then saved as quality-95 JPEG. Source frames are
    ~20 MP; YOLO downscales to imgsz=1280 every epoch *anyway*, so pre-shrinking to
    ~1536 keeps identical training detail but makes per-epoch JPEG decoding ~10x faster
    (the real bottleneck). Normalized YOLO boxes are scale-invariant, so labels are
    unchanged. With ``max_side == 0`` the original file is hard-linked (no re-encode)."""
    if dst.exists():
        dst.unlink()
    if max_side and max_side > 0:
        with Image.open(src) as im:
            im = im.convert("RGB")
            longest = max(im.size)
            if longest > max_side:
                scale = max_side / longest
                im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
            im.save(dst, format="JPEG", quality=95)
        return
    try:
        dst.hardlink_to(src)  # NTFS hard link: same inode, ~0 extra disk
    except OSError:
        shutil.copy2(src, dst)  # cross-volume / unsupported → real copy


def _split_for(flight: str, test: set[str], val: set[str]) -> str:
    if flight in test:
        return "test"
    if flight in val:
        return "val"
    return "train"


def build(src: Path, split_cfg: Path, out: Path, max_side: int) -> dict:
    cfg = yaml.safe_load(split_cfg.read_text(encoding="utf-8"))
    test_flights = set(cfg.get("test_flights") or [])
    val_flights = set(cfg.get("val_flights") or [])
    overlap = test_flights & val_flights
    if overlap:
        raise SystemExit(f"split.yaml lists flight(s) in BOTH test and val: {sorted(overlap)}")

    if out.exists():
        shutil.rmtree(out)
    for split in ("train", "val", "test"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    seen_flights: set[str] = set()
    per_split = {"train": 0, "val": 0, "test": 0}
    boxes = {"red": 0, "white": 0, "transition_dropped": 0}
    empty_frames = 0
    flight_rows: list[dict] = []

    for group in SOURCE_GROUPS:
        group_dir = src / group
        if not group_dir.is_dir():
            continue
        for flight_dir in sorted(p for p in group_dir.iterdir() if p.is_dir()):
            flight = flight_dir.name
            img_dir = flight_dir / "images"
            lbl_dir = flight_dir / "labels"
            if not img_dir.is_dir():
                continue
            if flight in seen_flights:
                raise SystemExit(f"flight {flight!r} appears under more than one group — ambiguous split")
            seen_flights.add(flight)
            split = _split_for(flight, test_flights, val_flights)

            images = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in IMG_EXTS)
            f_empty = 0
            for img in images:
                stem = f"{flight}__{img.stem}"
                _place_image(img, out / "images" / split / f"{stem}{img.suffix}", max_side)
                src_lbl = lbl_dir / f"{img.stem}.txt"
                filtered = _filter_label(src_lbl.read_text(encoding="utf-8")) if src_lbl.is_file() else ""
                (out / "labels" / split / f"{stem}.txt").write_text(filtered, encoding="utf-8")
                for line in filtered.splitlines():
                    cls = line.split()[0]
                    if cls == "0":
                        boxes["red"] += 1
                    elif cls == "1":
                        boxes["white"] += 1
                if src_lbl.is_file():
                    boxes["transition_dropped"] += sum(
                        1 for ln in src_lbl.read_text(encoding="utf-8").splitlines() if ln.split()[:1] == ["2"]
                    )
                if not filtered:
                    f_empty += 1
                    empty_frames += 1
            per_split[split] += len(images)
            flight_rows.append({"flight": flight, "group": group, "split": split,
                                "frames": len(images), "empty_frames": f_empty})

    missing = (test_flights | val_flights) - seen_flights
    data_yaml = out / "data.yaml"
    data_yaml.write_text(
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\nval: images/val\ntest: images/test\nnames:\n"
        + "".join(f"  {i}: {CLASS_NAMES[i]}\n" for i in sorted(CLASS_NAMES)),
        encoding="utf-8",
    )

    manifest = {
        "source": str(src), "split_config": str(split_cfg), "classes": CLASS_NAMES,
        "split_policy": "flight-level (no flight straddles train/val/test) — leak-free",
        "transition_handling": "class-2 (transition) boxes dropped; binary red/white detector",
        "image_handling": (
            f"downscaled to longest-edge {max_side}px (q95 JPEG) for fast per-epoch decode"
            if max_side else "hardlink (fallback copy), original resolution"
        ),
        "max_side": max_side,
        "frames_per_split": per_split, "boxes": boxes, "empty_frames": empty_frames,
        "flights": flight_rows,
        "split_flights_missing_on_disk": sorted(missing),
        "data_yaml": str(data_yaml),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, default=DEFAULT_SRC)
    p.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-side", type=int, default=1536,
                   help="Downscale longest edge to this many px for fast decode (0 = hardlink originals).")
    args = p.parse_args()
    manifest = build(args.src, args.split, args.out, args.max_side)
    print(json.dumps({k: manifest[k] for k in
                      ("frames_per_split", "boxes", "empty_frames", "max_side",
                       "split_flights_missing_on_disk", "data_yaml")},
                     indent=2))
    if manifest["frames_per_split"]["test"] == 0 or manifest["frames_per_split"]["val"] == 0:
        raise SystemExit("ERROR: empty val or test split — check split.yaml flight names vs on-disk flights.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
