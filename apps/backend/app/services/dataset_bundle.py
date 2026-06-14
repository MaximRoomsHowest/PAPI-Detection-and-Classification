"""Ingest an uploaded labelled YOLO dataset bundle (zip) into the canonical layout.

Accepts the common YOLO export shapes (CVAT export, ``images/``+``labels/`` tree,
optionally already split into train/val/test) and normalises them into the layout
in ``app.services.datasets`` so the trainer/evaluator consume them unchanged.
Class names come from a ``data.yaml`` / ``classes.txt`` / ``obj.names`` in the bundle,
else the project defaults. Extraction is zip-slip guarded; labels are validated.
"""

from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.datasets import (
    DEFAULT_CLASS_NAMES,
    IMAGE_SUFFIXES,
    class_names_from_yaml,
    ensure_dataset_dirs,
    format_yolo_label,
    parse_yolo_label_line,
    refresh_counts,
    split_for_name,
    write_data_yaml,
    write_split_files,
)

logger = logging.getLogger(__name__)


def is_zip(header: bytes) -> bool:
    # PK\x03\x04 (normal), PK\x05\x06 (empty), PK\x07\x08 (spanned).
    return header[:2] == b"PK" and header[2:4] in (b"\x03\x04", b"\x05\x06", b"\x07\x08")


def _safe_extract(zip_path: Path, dest: Path, max_extract_bytes: int | None = None) -> None:
    """Extract a zip with a zip-slip guard AND a total-decompressed-size cap.

    The HTTP layer only bounds the COMPRESSED upload; without an output cap a
    high-ratio deflate bomb could expand to hundreds of GB and exhaust the datasets
    volume. We stream each member in chunks and abort once the running total exceeds
    ``max_extract_bytes`` (None disables the cap).
    """
    dest = dest.resolve()
    total = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = (dest / member.filename).resolve()
            try:
                target.relative_to(dest)
            except ValueError as exc:
                logger.warning("Rejecting unsafe zip member (path traversal): %s", member.filename)
                raise ValueError("Dataset bundle contains an unsafe path.") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if max_extract_bytes is not None and total > max_extract_bytes:
                        raise ValueError("Dataset bundle expands beyond the allowed extracted size.")
                    out.write(chunk)


def _label_for_image(image: Path) -> Path | None:
    parts = list(image.parts)
    if "images" in parts:
        idx = len(parts) - 1 - parts[::-1].index("images")
        parts[idx] = "labels"
        candidate = Path(*parts).with_suffix(".txt")
        if candidate.exists():
            return candidate
    sibling = image.with_suffix(".txt")
    return sibling if sibling.exists() else None


def _split_from_path(image: Path) -> str | None:
    for part in image.parts:
        p = part.lower()
        if p == "train":
            return "train"
        if p in ("val", "valid", "validation"):
            return "val"
        if p == "test":
            return "test"
    return None


def _unique_name(root: Path, split: str, name: str) -> str:
    folder = root / "images" / split
    if not (folder / name).exists():
        return name
    stem, suffix = Path(name).stem, Path(name).suffix
    for i in range(1, 100000):
        candidate = f"{stem}_{i}{suffix}"
        if not (folder / candidate).exists():
            return candidate
    return f"{stem}_{uuid4().hex}{suffix}"


def _discover_class_names(raw: Path) -> dict[int, str]:
    for yaml_file in sorted(raw.rglob("*.yaml")) + sorted(raw.rglob("*.yml")):
        names = class_names_from_yaml(yaml_file)
        if names:
            return names
    for name_file in list(raw.rglob("classes.txt")) + list(raw.rglob("obj.names")):
        lines = [ln.strip() for ln in name_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            return {i: n for i, n in enumerate(lines)}
    return dict(DEFAULT_CLASS_NAMES)


def ingest_bundle(zip_path: Path, root: Path, max_extract_bytes: int | None = None) -> dict[str, Any]:
    """Extract + normalise a YOLO bundle into ``root``. Returns counts + class names.

    ``max_extract_bytes`` caps the total decompressed size (zip-bomb guard).
    """
    raw = root / "_raw"
    if raw.exists():
        shutil.rmtree(raw, ignore_errors=True)
    raw.mkdir(parents=True, exist_ok=True)
    try:
        _safe_extract(zip_path, raw, max_extract_bytes=max_extract_bytes)

        class_names = _discover_class_names(raw)
        n_classes = len(class_names)
        ensure_dataset_dirs(root)

        images = [p for p in raw.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES]
        if not images:
            raise ValueError("No images found in the uploaded bundle.")

        copied = 0
        for image in images:
            split = _split_from_path(image) or split_for_name(image.name)
            dest_name = _unique_name(root, split, image.name)
            shutil.copyfile(image, root / "images" / split / dest_name)

            label = _label_for_image(image)
            boxes: list[tuple[int, float, float, float, float]] = []
            if label is not None:
                for line in label.read_text(encoding="utf-8").splitlines():
                    parsed = parse_yolo_label_line(line, n_classes)  # raises on malformed
                    if parsed:
                        boxes.append(parsed)
            (root / "labels" / split / f"{Path(dest_name).stem}.txt").write_text(
                format_yolo_label(boxes), encoding="utf-8"
            )
            copied += 1
    finally:
        shutil.rmtree(raw, ignore_errors=True)

    write_split_files(root)
    yaml_path = write_data_yaml(root, class_names)
    n_train, n_val, n_test = refresh_counts(root)
    return {
        "class_names": class_names,
        "n_train": n_train,
        "n_val": n_val,
        "n_test": n_test,
        "data_yaml": str(yaml_path),
        "n_images": copied,
    }
