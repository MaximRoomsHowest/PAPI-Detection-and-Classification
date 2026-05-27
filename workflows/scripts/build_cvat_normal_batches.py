#!/usr/bin/env python
"""Build normal-lens CVAT annotation YOLO batches.

The batches are meant for CVAT's "Ultralytics YOLO Detection 1.0" importer.
They contain labels/config only and are paired with a sibling images.zip that
uses the exact same image paths. Manual corrections are preserved with the same
rule as the seed dataset: latest non-empty correction wins, and empty/missing
newer labels do not erase older labels.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import zipfile
from pathlib import Path

import yaml
from prepare_yolo_seed import (
    CLASS_NAMES,
    ManualSource,
    _merged_manual_labels,
    _parse_manual_source,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_METADATA = REPO_ROOT / "data" / "interim" / "images_metadata.csv"
DEFAULT_OUT_ROOT = REPO_ROOT / "data" / "cvat" / "normal_batches"
DEFAULT_ASSISTED_ZIP = REPO_ROOT / "data" / "cvat" / "papi_yolov26m_seed300_assisted_annotations_conf050.zip"
DEFAULT_MANUAL_SOURCES = [
    "data/annotations/manual_corrections/cvat_030:30",
    "data/annotations/manual_corrections/cvat_080:80",
    "data/annotations/manual_corrections/cvat_140:167",
    "data/annotations/manual_corrections/batch_001_corrected_300:300",
]


def _resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _flat_name(row: dict[str, str]) -> str:
    return f"{row['folder']}__{row['file']}"


def _normal_rows(metadata_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with metadata_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (
                row["camera"] == "WideCamera"
                and int(row["image_width"]) == 5280
                and int(row["image_height"]) == 3956
            ):
                rows.append(row)
    return rows


def _read_assisted_labels(zip_path: Path) -> dict[str, str]:
    if not zip_path.exists():
        return {}

    return _read_label_zip(zip_path)


def _read_existing_batch_labels(batch_root: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for zip_path in sorted(batch_root.glob("batch_*/annotations.zip")):
        labels.update(_read_label_zip(zip_path))
    return labels


def _available_manual_sources(manual_sources: list[ManualSource]) -> list[ManualSource]:
    available: list[ManualSource] = []
    for source in manual_sources:
        if (source.path / "train.txt").exists():
            available.append(source)
        else:
            print(f"Skipping missing manual source: {source.path}")
    return available


def _read_label_zip(zip_path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            path = Path(name)
            if len(path.parts) < 3 or path.parts[-3:-1] != ("labels", "train") or path.suffix != ".txt":
                continue
            text = archive.read(name).decode("utf-8")
            if text.strip():
                labels[path.stem] = text if text.endswith("\n") else f"{text}\n"
    return labels


def _write_label(label_path: Path, text: str) -> int:
    label_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.write_text(text, encoding="utf-8")
    return sum(1 for line in text.splitlines() if line.strip())


def _write_zip(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file() and path.name not in {
                "annotations.zip",
                "images.zip",
            }:
                archive.write(path, path.relative_to(source_dir).as_posix())


def _chunks(items: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def build_batches(
    metadata_path: Path,
    out_root: Path,
    manual_sources: list[ManualSource],
    assisted_zip: Path,
    batch_size: int,
) -> None:
    normal_rows = _normal_rows(metadata_path)
    manual_labels = _merged_manual_labels(_available_manual_sources(manual_sources), exclude_indices=set())
    assisted_labels = _read_assisted_labels(assisted_zip)
    if not assisted_labels:
        assisted_labels = _read_existing_batch_labels(out_root)

    if out_root.exists():
        for batch_dir in out_root.glob("batch_*"):
            for child in batch_dir.iterdir():
                if child.name == "images.zip":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    else:
        out_root.mkdir(parents=True)
    out_root.mkdir(parents=True, exist_ok=True)

    totals = {
        "frames": 0,
        "manual_preserved": 0,
        "assisted_reused": 0,
        "empty": 0,
        "objects": 0,
    }

    for batch_index, batch_rows in enumerate(_chunks(normal_rows, batch_size), start=1):
        batch_name = f"batch_{batch_index:03d}"
        batch_dir = out_root / batch_name
        batch_dir.mkdir(parents=True, exist_ok=True)
        labels_dir = batch_dir / "labels" / "train"
        train_entries: list[str] = []
        batch_counts = {
            "frames": 0,
            "manual_preserved": 0,
            "assisted_reused": 0,
            "empty": 0,
            "objects": 0,
        }

        for row in batch_rows:
            flat_name = _flat_name(row)
            stem = Path(flat_name).stem
            train_entries.append(f"images/train/{flat_name}")

            if stem in manual_labels and manual_labels[stem].strip():
                label_text = manual_labels[stem]
                batch_counts["manual_preserved"] += 1
            elif stem in assisted_labels:
                label_text = assisted_labels[stem]
                batch_counts["assisted_reused"] += 1
            else:
                label_text = ""
                batch_counts["empty"] += 1

            batch_counts["objects"] += _write_label(labels_dir / f"{stem}.txt", label_text)
            batch_counts["frames"] += 1

        (batch_dir / "train.txt").write_text("\n".join(train_entries) + "\n", encoding="utf-8")
        (batch_dir / "val.txt").write_text("", encoding="utf-8")
        data_yaml = {
            "path": "./",
            "train": "train.txt",
            "names": CLASS_NAMES,
        }
        with (batch_dir / "data.yaml").open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data_yaml, fh, sort_keys=False)

        zip_path = batch_dir / "annotations.zip"
        _write_zip(batch_dir, zip_path)

        for key, value in batch_counts.items():
            totals[key] += value
        print(f"{batch_name}: {batch_counts} -> {zip_path}")

    print(f"Normal frames: {len(normal_rows)}")
    print(f"Manual labels available: {len(manual_labels)}")
    print(f"Assisted labels available: {len(assisted_labels)}")
    print(f"Totals: {totals}")
    print(f"Wrote batch root: {out_root}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--assisted-zip", type=Path, default=DEFAULT_ASSISTED_ZIP)
    parser.add_argument("--batch-size", type=int, default=300)
    parser.add_argument(
        "--manual-source",
        action="append",
        default=DEFAULT_MANUAL_SOURCES,
        help="Manual source as path:limit. Can be passed multiple times; latest non-empty wins.",
    )
    args = parser.parse_args()

    manual_sources = [
        ManualSource(_resolve_repo_path(source.path), source.limit)
        for source in (_parse_manual_source(value) for value in args.manual_source)
    ]
    build_batches(
        metadata_path=_resolve_repo_path(args.metadata),
        out_root=_resolve_repo_path(args.out_root),
        manual_sources=manual_sources,
        assisted_zip=_resolve_repo_path(args.assisted_zip),
        batch_size=args.batch_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
