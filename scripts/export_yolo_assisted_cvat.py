#!/usr/bin/env python
"""Export YOLO-assisted lamp-state annotations for an existing CVAT task.

The script reads the image list from a CVAT Ultralytics annotations-only export,
copies the matching raw images into a temporary prediction folder, runs a trained
YOLO detector, and writes a new annotations-only Ultralytics YOLO Detection 1.0
zip for CVAT import.

Manually corrected CVAT labels can be supplied as one or more correction directories.
Those labels are preferred over predictions. Older CVAT task IDs are remapped:

    1 -> 0 papi_light_red
    2 -> 1 papi_light_white

Newer normalized YOLO exports already use zero-based IDs and are kept as-is.
Transition is no longer a detector class; any transition rows fail validation.
When multiple correction exports are supplied, latest non-empty label wins. Missing or empty
label files in newer exports do not erase older corrected labels.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import zipfile
from pathlib import Path
from typing import NamedTuple

import yaml
from PIL import Image
from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASK = REPO_ROOT / "data" / "cvat" / "day_batches" / "batch_007"
DEFAULT_MANUAL = REPO_ROOT / "data" / "annotations" / "manual_corrections" / "batch_001_corrected_300"
DEFAULT_RAW = REPO_ROOT / "data" / "raw"
DEFAULT_METADATA = REPO_ROOT / "data" / "interim" / "images_metadata.csv"
DEFAULT_MODEL = REPO_ROOT / "models" / "serving" / "best.pt"
DEFAULT_OUT = REPO_ROOT / "data" / "work" / "assisted_cvat_export"
DEFAULT_ZIP = REPO_ROOT / "data" / "cvat" / "day_batches" / "batch_007" / "annotations.zip"
DEFAULT_PREDICT_IMAGES = REPO_ROOT / "data" / "work" / "assisted_predictions" / "images"

CLASS_NAMES = {
    0: "papi_light_red",
    1: "papi_light_white",
}
MANUAL_REMAP = {
    1: 0,
    2: 1,
}


class ManualSource(NamedTuple):
    path: Path
    limit: int


def _flat_name_from_entry(entry: str) -> str:
    return Path(entry.strip()).name


def _source_from_flat_name(flat_name: str, raw_dir: Path) -> Path:
    folder, filename = flat_name.split("__", 1)
    return raw_dir / folder / f"{Path(filename).stem}.JPG"


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _read_entries(task_dir: Path) -> list[str]:
    train_txt = task_dir / "train.txt"
    entries = [line.strip() for line in train_txt.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not entries:
        raise ValueError(f"No train entries found in {train_txt}")
    return entries


def _prepare_prediction_images(entries: list[str], raw_dir: Path, image_dir: Path) -> list[Path]:
    _reset_dir(image_dir)
    image_paths: list[Path] = []
    for entry in entries:
        flat_name = _flat_name_from_entry(entry)
        src = _source_from_flat_name(flat_name, raw_dir)
        if not src.exists():
            raise FileNotFoundError(f"Raw image not found for {flat_name}: {src}")
        dst = image_dir / flat_name
        shutil.copy2(src, dst)
        image_paths.append(dst)
    return image_paths


def _source_uses_zero_based_labels(label_path: Path) -> bool:
    source_dir = label_path.parents[2]
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


def _manual_label_text(label_path: Path) -> str:
    if not label_path.exists():
        return ""

    rows = [line.split() for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        return ""

    already_zero_based = _source_uses_zero_based_labels(label_path)

    lines: list[str] = []
    for parts in rows:
        class_id = int(parts[0])
        if already_zero_based:
            if class_id not in CLASS_NAMES:
                raise ValueError(f"Unsupported detector class {class_id} in {label_path}")
            lines.append(" ".join(parts))
        elif class_id in MANUAL_REMAP:
            lines.append(" ".join([str(MANUAL_REMAP[class_id]), *parts[1:]]))
        else:
            raise ValueError(f"Unsupported detector class {class_id} in {label_path}")
    return "\n".join(lines) + ("\n" if lines else "")


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


def _read_source_entries(source: ManualSource) -> list[str]:
    train_txt = source.path / "train.txt"
    entries = [line.strip() for line in train_txt.read_text(encoding="utf-8").splitlines() if line.strip()]
    return entries[: source.limit]


def _merged_manual_labels(sources: list[ManualSource], exclude_indices: set[int]) -> tuple[dict[str, str], set[str]]:
    labels_by_stem: dict[str, str] = {}
    forced_empty_stems: set[str] = set()
    for source in sources:
        entries = _read_source_entries(source)
        for one_based_index, entry in enumerate(entries, start=1):
            stem = Path(_flat_name_from_entry(entry)).stem
            if one_based_index in exclude_indices:
                labels_by_stem[stem] = ""
                forced_empty_stems.add(stem)
                continue
            text = _manual_label_text(source.path / "labels" / "train" / f"{stem}.txt")
            if text.strip():
                labels_by_stem[stem] = text
    return labels_by_stem, forced_empty_stems


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


def _prediction_label_text(result, conf: float) -> str:
    if result.boxes is None or len(result.boxes) == 0:
        return ""

    lines: list[str] = []
    boxes = result.boxes
    for class_id, confidence, xywhn in zip(boxes.cls, boxes.conf, boxes.xywhn, strict=True):
        class_index = int(class_id.item())
        if class_index not in CLASS_NAMES or float(confidence.item()) < conf:
            continue
        cx, cy, width, height = (float(v) for v in xywhn.tolist())
        lines.append(f"{class_index} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}")
    return "\n".join(lines) + ("\n" if lines else "")


def _zip_dir(out_dir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in out_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir))


def export_assisted_annotations(
    task_dir: Path,
    manual_sources: list[ManualSource],
    raw_dir: Path,
    metadata_path: Path,
    model_path: Path,
    out_dir: Path,
    zip_path: Path,
    image_dir: Path,
    image_size: int,
    conf: float,
    max_det: int,
    device: str,
    exclude_manual_indices: set[int],
    predict_group: str,
) -> None:
    entries = _read_entries(task_dir)
    labels_by_stem, forced_empty_stems = _merged_manual_labels(manual_sources, exclude_manual_indices)
    metadata = _metadata_lookup(metadata_path)

    predicted_candidate_entries: list[str] = []
    skipped_prediction_group_count = 0
    manual_preserved_count = 0
    for entry in entries:
        flat_name = _flat_name_from_entry(entry)
        stem = Path(flat_name).stem
        if stem in labels_by_stem:
            manual_preserved_count += 1
            continue
        if predict_group != "all" and _image_group(flat_name, raw_dir, metadata) != predict_group:
            skipped_prediction_group_count += 1
            continue
        predicted_candidate_entries.append(entry)

    _prepare_prediction_images(predicted_candidate_entries, raw_dir, image_dir)
    predictions: dict[str, str] = {}
    if predicted_candidate_entries:
        model = YOLO(str(model_path))
        for result in model.predict(
            source=str(image_dir),
            imgsz=image_size,
            conf=conf,
            max_det=max_det,
            device=device,
            stream=True,
            verbose=False,
        ):
            predictions[Path(result.path).stem] = _prediction_label_text(result, conf)

    _reset_dir(out_dir)
    labels_dir = out_dir / "labels" / "train"
    labels_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "labels" / "val").mkdir(parents=True, exist_ok=True)

    predicted_count = 0
    predicted_object_files = 0
    empty_count = 0
    object_count = 0
    for entry in entries:
        flat_name = _flat_name_from_entry(entry)
        stem = Path(flat_name).stem
        if stem in labels_by_stem:
            label_text = labels_by_stem[stem]
        else:
            label_text = predictions.get(stem, "")
            if stem in predictions:
                predicted_count += 1
                if label_text.strip():
                    predicted_object_files += 1
        if not label_text.strip():
            empty_count += 1
        object_count += sum(1 for line in label_text.splitlines() if line.strip())
        (labels_dir / f"{stem}.txt").write_text(label_text, encoding="utf-8")

    (out_dir / "train.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
    (out_dir / "val.txt").write_text("", encoding="utf-8")
    data_yaml = {
        "path": "./",
        "train": "train.txt",
        "val": "val.txt",
        "names": CLASS_NAMES,
    }
    with (out_dir / "data.yaml").open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data_yaml, fh, sort_keys=False)

    _zip_dir(out_dir, zip_path)
    print(f"Wrote assisted CVAT annotations -> {out_dir}")
    print(f"Wrote zip -> {zip_path}")
    print(f"Images listed: {len(entries)}")
    print(f"Manual labels preserved: {manual_preserved_count}")
    print(f"Manual indices forced empty: {len(forced_empty_stems)}")
    print(f"Prediction candidates: {len(predicted_candidate_entries)}")
    print(f"Predicted label files written: {predicted_count}")
    print(f"Predicted non-empty label files: {predicted_object_files}")
    print(f"Skipped prediction by group: {skipped_prediction_group_count}")
    print(f"Empty label files: {empty_count}")
    print(f"Objects: {object_count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, default=DEFAULT_TASK)
    parser.add_argument("--manual-dir", type=Path, default=DEFAULT_MANUAL)
    parser.add_argument(
        "--manual-source",
        action="append",
        default=[],
        help="Manual correction source formatted as path:limit. Repeat in priority order.",
    )
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--zip-out", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--predict-images", type=Path, default=DEFAULT_PREDICT_IMAGES)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument(
        "--conf",
        type=float,
        default=0.10,
        help="Minimum confidence for model-predicted annotations. Manual labels are always kept.",
    )
    parser.add_argument("--device", default="0")
    parser.add_argument(
        "--max-det",
        type=int,
        default=4,
        help="Maximum model detections per image before writing YOLO labels.",
    )
    parser.add_argument(
        "--manual-limit",
        type=int,
        default=30,
        help="Only trust the first N entries from the manual correction train.txt.",
    )
    parser.add_argument(
        "--exclude-manual-indices",
        nargs="*",
        default=[],
        help="1-based manual train.txt indices or ranges to force empty, e.g. 96-101.",
    )
    parser.add_argument(
        "--predict-group",
        choices=("all", "normal", "zoom_cropped"),
        default="normal",
        help="Only run YOLO predictions on this metadata/dimension group.",
    )
    args = parser.parse_args()
    manual_sources = (
        [_parse_manual_source(source) for source in args.manual_source]
        if args.manual_source
        else [ManualSource(args.manual_dir, args.manual_limit)]
    )

    export_assisted_annotations(
        task_dir=args.task_dir,
        manual_sources=manual_sources,
        raw_dir=args.raw_dir,
        metadata_path=args.metadata,
        model_path=args.model,
        out_dir=args.out_dir,
        zip_path=args.zip_out,
        image_dir=args.predict_images,
        image_size=args.imgsz,
        conf=args.conf,
        max_det=args.max_det,
        device=args.device,
        exclude_manual_indices=_parse_excluded_indices(args.exclude_manual_indices),
        predict_group=args.predict_group,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
