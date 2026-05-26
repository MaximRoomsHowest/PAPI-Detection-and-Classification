"""Build a CVAT-importable Ultralytics YOLO Detection 1.0 bundle.

CVAT's "Ultralytics YOLO Detection 1.0" importer (datumaro's `yolo_ultralytics` format)
expects:

    <out_dir>/
      data.yaml                          top-level config (train, val, names)
      train.txt                          list of training image paths ("./images/train/<x>.JPG")
      val.txt                            list of val image paths
      images/
        train/
          <flat_name>.JPG
        val/
          <flat_name>.JPG
      labels/
        train/
          <flat_name>.txt                YOLO label: `<class_id> <cx> <cy> <w> <h>` normalized
        val/
          <flat_name>.txt

Datumaro detects this layout by `require_file('data.yaml')` and requires both `train` and
`val` subsets to exist. Train/val assignment uses the `split` column on each row (train flights
-> train; val/test flights -> val). Frames with no split default to train.

The verification context (`reason`, `global_state`, `target_runway`, etc.) is NOT carried
inside the zip — YOLO has no per-image metadata. Join `data/interim/verification_sample.csv`
on `(folder, file)` to recover those columns.
"""

from __future__ import annotations

import shutil
import zipfile
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from .io import YOLO_CLASS_NAMES


def _reset_bundle_dir(out_dir: Path) -> None:
    """Remove generated bundle contents that can otherwise go stale."""
    for rel in ("images", "labels"):
        path = out_dir / rel
        if path.exists():
            shutil.rmtree(path)

    for rel in ("train.txt", "val.txt", "data.yaml"):
        path = out_dir / rel
        if path.exists():
            path.unlink()


def _yolo_label_text(label_path: Path) -> str:
    """Return label-file contents, or empty string for frames with no auto-label."""
    if not label_path.exists():
        return ""
    return label_path.read_text(encoding="utf-8")


def _subset_for(row: dict[str, Any]) -> str:
    """Map a row to either 'train' or 'val' using its `split` column."""
    split = row.get("split", "train")
    return "val" if split in ("val", "test") else "train"


def _image_name_for(folder: str, fname: str, image_name_mode: str) -> str:
    if image_name_mode == "flat":
        return f"{folder}__{fname}"
    if image_name_mode == "original":
        return fname
    raise ValueError(f"Unsupported image_name_mode: {image_name_mode}")


def build_ultralytics(
    rows: Iterable[dict[str, Any]],
    raw_dir: Path,
    labels_dir: Path,
    out_dir: Path,
    include_images: bool = True,
    image_name_mode: str = "flat",
    class_names: dict[int, str] | None = None,
) -> Path:
    """Materialize a CVAT Ultralytics YOLO Detection 1.0 bundle. Returns path to data.yaml."""
    _reset_bundle_dir(out_dir)

    # Pre-create both required subset directories so datumaro is happy even if a subset is empty.
    for subset in ("train", "val"):
        if include_images:
            (out_dir / "images" / subset).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / subset).mkdir(parents=True, exist_ok=True)

    image_paths_per_subset: dict[str, list[str]] = defaultdict(list)
    written_label_paths: set[Path] = set()

    for row in rows:
        folder = row["folder"]
        fname = row["file"]
        image_name = _image_name_for(folder, fname, image_name_mode)
        subset = _subset_for(row)

        if include_images:
            src_img = raw_dir / folder / fname
            dst_img = out_dir / "images" / subset / image_name
            if not src_img.exists():
                raise FileNotFoundError(f"Sample image not found: {src_img}")
            shutil.copy2(src_img, dst_img)

        # Label (empty file is fine — means "no objects in this image")
        src_label = labels_dir / folder / (Path(fname).stem + ".txt")
        dst_label = out_dir / "labels" / subset / (Path(image_name).stem + ".txt")
        if dst_label in written_label_paths:
            raise ValueError(f"Duplicate output label path: {dst_label}")
        written_label_paths.add(dst_label)
        dst_label.write_text(_yolo_label_text(src_label), encoding="utf-8")

        # The "./" prefix is required by Ultralytics per
        # https://github.com/ultralytics/ultralytics/blob/main/ultralytics/data/utils.py
        image_paths_per_subset[subset].append(f"./images/{subset}/{image_name}")

    # Write subset list files (train.txt, val.txt) — empty file if subset has no frames
    for subset in ("train", "val"):
        lines = image_paths_per_subset.get(subset, [])
        (out_dir / f"{subset}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    # data.yaml — Ultralytics convention
    yaml_doc = {
        "path": "./",
        "train": "train.txt",
        "val": "val.txt",
        "names": {
            i: (class_names or YOLO_CLASS_NAMES)[i]
            for i in sorted(class_names or YOLO_CLASS_NAMES)
        },
    }
    data_yaml = out_dir / "data.yaml"
    with data_yaml.open("w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_doc, f, sort_keys=False, allow_unicode=True)
    return data_yaml


def zip_bundle(out_dir: Path, zip_path: Path) -> Path:
    """Zip `out_dir` (Ultralytics YOLO Detection 1.0 layout) for upload to CVAT."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    skip_names = {".gitkeep"}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for p in out_dir.rglob("*"):
            if not p.is_file() or p.suffix.lower() == ".zip" or p.name in skip_names:
                continue
            zf.write(p, arcname=p.relative_to(out_dir))
    return zip_path
