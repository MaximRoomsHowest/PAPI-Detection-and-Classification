#!/usr/bin/env python
"""Prepare manually corrected CVAT labels for YOLO training.

CVAT correction exports keep labels under `labels/train` but do not include images.
This script copies matching raw images and normalizes label IDs. Older CVAT
exports used one-based task IDs:

    1 -> 0 papi_light_red
    2 -> 1 papi_light_white

Newer normalized YOLO exports already use zero-based IDs and are kept as-is.
Transition is no longer a detector class; any transition rows fail validation.
When multiple correction exports are provided, latest non-empty label wins. Missing or empty
label files in newer exports do not erase older corrected labels.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path
from typing import NamedTuple

import yaml
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CVAT = REPO_ROOT / "data" / "annotations" / "manual_corrections" / "cvat_140"
DEFAULT_RAW = REPO_ROOT / "data" / "raw"
DEFAULT_OUT = REPO_ROOT / "data" / "datasets" / "yolo" / "papi_lamp_seed"
DEFAULT_METADATA = REPO_ROOT / "data" / "interim" / "images_metadata.csv"

CLASS_REMAP = {
    1: 0,
    2: 1,
}
CLASS_NAMES = {
    0: "papi_light_red",
    1: "papi_light_white",
}


class ManualSource(NamedTuple):
    path: Path
    limit: int


def _source_from_flat_name(flat_name: str, raw_dir: Path) -> Path:
    folder, filename = flat_name.split("__", 1)
    return raw_dir / folder / f"{Path(filename).stem}.JPG"


def _source_uses_zero_based_labels(src: Path) -> bool:
    source_dir = src.parents[2]
    data_yaml = source_dir / "data.yaml"
    if data_yaml.exists():
        data = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
        names = data.get("names", {})
        if isinstance(names, dict):
            normalized = {int(key): value for key, value in names.items()}
            if normalized.get(0) == CLASS_NAMES[0]:
                return True
            if normalized.get(1) == CLASS_NAMES[0]:
                return False
    return True


def _remap_label_text(src: Path) -> str:
    rows = [line.split() for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return ""

    already_zero_based = _source_uses_zero_based_labels(src)

    lines: list[str] = []
    for parts in rows:
        class_id = int(parts[0])
        if already_zero_based:
            if class_id not in CLASS_NAMES:
                raise ValueError(f"Unsupported detector class {class_id} in {src}")
            lines.append(" ".join(parts))
        elif class_id in CLASS_REMAP:
            lines.append(" ".join([str(CLASS_REMAP[class_id]), *parts[1:]]))
        else:
            raise ValueError(f"Unsupported detector class {class_id} in {src}")
    return "\n".join(lines) + ("\n" if lines else "")


def _write_label_text(text: str, dst: Path) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    return sum(1 for line in text.splitlines() if line.strip())


def _split_for_entries(limit: int, val_count: int, split_mode: str) -> list[str]:
    train_count = max(1, limit - val_count)
    if split_mode == "sequential":
        return ["train"] * train_count + ["val"] * (limit - train_count)
    if split_mode == "interleaved":
        stride = max(1, round(limit / max(1, val_count)))
        val_indices = {index for index in range(limit) if (index + 1) % stride == 0}
        if len(val_indices) > val_count:
            val_indices = set(sorted(val_indices)[:val_count])
        index = limit - 1
        while len(val_indices) < val_count and index >= 0:
            val_indices.add(index)
            index -= 1
        return ["val" if index in val_indices else "train" for index in range(limit)]
    raise ValueError(f"Unsupported split mode: {split_mode}")


def _parse_excluded_indices(values: list[str]) -> set[int]:
    excluded: set[int] = set()
    for value in values:
        for part in value.split(","):
            item = part.strip()
            if not item:
                continue
            if "-" in item:
                start_text, end_text = item.split("-", 1)
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    raise ValueError(f"Invalid index range: {item}")
                excluded.update(range(start, end + 1))
            else:
                excluded.add(int(item))
    return excluded


def _parse_manual_source(value: str) -> ManualSource:
    if ":" not in value:
        raise ValueError(f"Manual source must be formatted as path:limit, got: {value}")
    path_text, limit_text = value.rsplit(":", 1)
    return ManualSource(Path(path_text), int(limit_text))


def _flat_name_from_entry(entry: str) -> str:
    return Path(entry.strip()).name


def _read_entries(cvat_dir: Path, limit: int) -> list[str]:
    entries = [
        line.strip()
        for line in (cvat_dir / "train.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:limit]
    if len(entries) < limit:
        raise ValueError(f"Requested {limit} entries but only found {len(entries)} in {cvat_dir / 'train.txt'}")
    return entries


def _manual_stem_order(source: ManualSource, exclude_indices: set[int]) -> dict[str, str]:
    labels_by_stem: dict[str, str] = {}
    entries = _read_entries(source.path, source.limit)
    for one_based_index, entry in enumerate(entries, start=1):
        flat_name = _flat_name_from_entry(entry)
        stem = Path(flat_name).stem
        if one_based_index in exclude_indices:
            labels_by_stem[stem] = ""
            continue
        label_path = source.path / "labels" / "train" / f"{stem}.txt"
        if not label_path.exists():
            continue
        text = _remap_label_text(label_path)
        if text.strip():
            labels_by_stem[stem] = text
    return labels_by_stem


def _merged_manual_labels(sources: list[ManualSource], exclude_indices: set[int]) -> dict[str, str]:
    labels_by_stem: dict[str, str] = {}
    for source in sources:
        labels_by_stem.update(_manual_stem_order(source, exclude_indices))
    return labels_by_stem


def _metadata_lookup(metadata_path: Path) -> dict[tuple[str, str], tuple[str, int, int]]:
    if not metadata_path.exists():
        return {}
    lookup: dict[tuple[str, str], tuple[str, int, int]] = {}
    with metadata_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            lookup[(row["folder"], row["file"])] = (
                row["camera"],
                int(row["image_width"]),
                int(row["image_height"]),
            )
    return lookup


def _image_group(flat_name: str, raw_dir: Path, metadata: dict[tuple[str, str], tuple[str, int, int]]) -> str:
    folder, filename = flat_name.split("__", 1)
    jpg_name = f"{Path(filename).stem}.JPG"
    meta = metadata.get((folder, jpg_name))
    if meta is not None:
        camera, width, height = meta
    else:
        with Image.open(_source_from_flat_name(flat_name, raw_dir)) as image:
            width, height = image.size
        camera = ""
    return "normal" if camera == "WideCamera" and (width, height) == (5280, 3956) else "zoom_cropped"


def prepare_dataset(
    cvat_dir: Path,
    manual_sources: list[ManualSource],
    raw_dir: Path,
    out_dir: Path,
    limit: int,
    val_count: int,
    split_mode: str,
    allow_missing_labels_as_empty: bool,
    exclude_indices: set[int],
    image_group: str,
    metadata_path: Path,
) -> None:
    entries = _read_entries(cvat_dir, limit)
    sources = manual_sources or [ManualSource(cvat_dir, limit)]
    labels_by_stem = _merged_manual_labels(sources, exclude_indices)
    metadata = _metadata_lookup(metadata_path)

    if out_dir.exists():
        shutil.rmtree(out_dir)

    filtered_entries: list[str] = []
    skipped_groups = {"normal": 0, "zoom_cropped": 0}
    for entry in entries:
        flat_name = _flat_name_from_entry(entry)
        group = _image_group(flat_name, raw_dir, metadata)
        if image_group != "all" and group != image_group:
            skipped_groups[group] += 1
            continue
        filtered_entries.append(entry)

    subsets = _split_for_entries(len(filtered_entries), min(val_count, max(0, len(filtered_entries) - 1)), split_mode)
    object_counts = {"train": 0, "val": 0}
    image_counts = {"train": 0, "val": 0}
    empty_counts = {"train": 0, "val": 0}

    for entry, subset in zip(filtered_entries, subsets, strict=True):
        flat_name = Path(entry).name
        stem = Path(flat_name).stem
        src_image = _source_from_flat_name(flat_name, raw_dir)
        if not src_image.exists():
            raise FileNotFoundError(f"Raw image not found for {flat_name}: {src_image}")

        dst_image = out_dir / "images" / subset / flat_name
        dst_image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_image, dst_image)

        label_text = labels_by_stem.get(stem, "")
        if not label_text and not allow_missing_labels_as_empty and stem not in labels_by_stem:
            raise FileNotFoundError(f"No corrected label found for {flat_name} in manual sources")
        dst_label = out_dir / "labels" / subset / f"{stem}.txt"
        object_counts[subset] += _write_label_text(label_text, dst_label)
        if not label_text.strip():
            empty_counts[subset] += 1
        image_counts[subset] += 1

    data_yaml = {
        "path": str(out_dir.resolve()).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "names": CLASS_NAMES,
    }
    with (out_dir / "data.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data_yaml, fh, sort_keys=False)

    print(f"Wrote YOLO seed dataset -> {out_dir}")
    print(f"Images: {image_counts}")
    print(f"Empty labels: {empty_counts}")
    print(f"Objects: {object_counts}")
    print(f"Skipped by group: {skipped_groups}")
    print(f"Classes: {CLASS_NAMES}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cvat-dir", type=Path, default=DEFAULT_CVAT)
    parser.add_argument(
        "--manual-source",
        action="append",
        default=[],
        help="Manual correction source formatted as path:limit. Repeat in priority order.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--val-count", type=int, default=6)
    parser.add_argument(
        "--split-mode",
        choices=("sequential", "interleaved"),
        default="sequential",
        help="Use interleaved for chronological CVAT corrections so val covers more of the sequence.",
    )
    parser.add_argument(
        "--allow-missing-labels-as-empty",
        action="store_true",
        help="Treat missing CVAT label files as corrected empty/background images.",
    )
    parser.add_argument(
        "--exclude-indices",
        nargs="*",
        default=[],
        help="1-based train.txt indices or ranges to force empty, e.g. --exclude-indices 96-101.",
    )
    parser.add_argument(
        "--image-group",
        choices=("all", "normal", "zoom_cropped"),
        default="all",
        help="Filter output by camera/dimension group.",
    )
    args = parser.parse_args()

    prepare_dataset(
        args.cvat_dir,
        [_parse_manual_source(source) for source in args.manual_source],
        args.raw_dir,
        args.out_dir,
        args.limit,
        args.val_count,
        args.split_mode,
        args.allow_missing_labels_as_empty,
        _parse_excluded_indices(args.exclude_indices),
        args.image_group,
        args.metadata,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
