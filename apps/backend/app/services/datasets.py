"""Filesystem helpers for YOLO-format datasets.

A dataset directory under ``PAPI_DATASETS_DIR/<id>/`` mirrors exactly what the
existing trainer/evaluator scripts expect, so neither needs changing::

    images/{train,val,test}/*.jpg
    labels/{train,val,test}/*.txt        # YOLO: "class cx cy w h" (normalized)
    train.txt val.txt test.txt           # image paths, one per line
    data.yaml                            # path + split files + class names

Assisted-labeling datasets additionally use a staging area::

    images/_staging/*.jpg                # raw uploads awaiting review
    labels/_candidates/*.txt             # model-predicted candidate labels
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import Settings

# Canonical PAPI detection classes (kept in lockstep with the trainer/evaluator).
DEFAULT_CLASS_NAMES: dict[int, str] = {
    0: "papi_light_red",
    1: "papi_light_white",
    2: "papi_light_transition",
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = ("train", "val", "test")
STAGING_SPLIT = "_staging"
CANDIDATES_DIR = "_candidates"


def dataset_root(settings: Settings, dataset_id: str) -> Path:
    """Absolute dataset directory, guarded against id path-traversal."""
    safe = dataset_id.replace("\\", "/").strip("/")
    if not safe or "/" in safe or safe in (".", ".."):
        raise ValueError("Invalid dataset id.")
    return (settings.datasets_dir / safe).resolve()


def ensure_dataset_dirs(root: Path, *, staging: bool = False) -> None:
    for split in SPLITS:
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
    if staging:
        (root / "images" / STAGING_SPLIT).mkdir(parents=True, exist_ok=True)
        (root / "labels" / CANDIDATES_DIR).mkdir(parents=True, exist_ok=True)


def split_for_name(name: str) -> str:
    """Deterministic, stable 80/10/10 split keyed on the filename.

    A hash bucket keeps the same image in the same split across re-ingests, and
    needs no RNG (which is unavailable in some execution contexts here).
    """
    bucket = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 10
    if bucket == 0:
        return "val"
    if bucket == 1:
        return "test"
    return "train"


def parse_yolo_label_line(line: str, n_classes: int) -> tuple[int, float, float, float, float] | None:
    """Parse + validate one YOLO label line, or None if blank.

    Raises ValueError on a malformed line (wrong arity, non-numeric, class out of
    range, coord outside [0,1]) so bundle ingestion can reject a bad dataset early.
    """
    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split()
    if len(parts) != 5:
        raise ValueError(f"Label line must have 5 fields, got {len(parts)}: {stripped!r}")
    try:
        class_id = int(float(parts[0]))
        cx, cy, w, h = (float(p) for p in parts[1:])
    except ValueError as exc:
        raise ValueError(f"Non-numeric label field in {stripped!r}") from exc
    if not (0 <= class_id < n_classes):
        raise ValueError(f"Label class_id {class_id} out of range for {n_classes} classes.")
    for value in (cx, cy, w, h):
        if not (0.0 <= value <= 1.0):
            raise ValueError(f"Label coordinate {value} outside [0,1] in {stripped!r}")
    return class_id, cx, cy, w, h


def format_yolo_label(boxes: list[tuple[int, float, float, float, float]]) -> str:
    """Render boxes (class, cx, cy, w, h) as YOLO label-file text."""
    return "".join(
        f"{c} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n" for c, cx, cy, w, h in boxes
    )


def count_images(root: Path, split: str) -> int:
    folder = root / "images" / split
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)


def write_split_files(root: Path) -> None:
    """(Re)write train.txt/val.txt/test.txt from the images present in each split."""
    for split in SPLITS:
        folder = root / "images" / split
        lines = []
        if folder.is_dir():
            for image in sorted(folder.iterdir()):
                if image.suffix.lower() in IMAGE_SUFFIXES:
                    lines.append(f"./images/{split}/{image.name}")
        (root / f"{split}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_data_yaml(root: Path, class_names: dict[int, str]) -> Path:
    """Write data.yaml in the exact shape the trainer/evaluator consume."""
    names_block = "".join(f"  {i}: {class_names[i]}\n" for i in sorted(class_names))
    yaml_text = (
        f"path: {root.resolve().as_posix()}\n"
        "train: train.txt\n"
        "val: val.txt\n"
        "test: test.txt\n"
        "names:\n" + names_block
    )
    path = root / "data.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    return path


def class_names_from_yaml(yaml_path: Path) -> dict[int, str] | None:
    """Best-effort parse of a ``names:`` block from a dataset data.yaml.

    Supports both the ``  0: name`` mapping form this project writes and the
    ``names: [a, b]`` list form some exports use.
    """
    try:
        import yaml

        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing/garbage yaml just means "use defaults"
        return None
    if not isinstance(data, dict):
        return None
    names = data.get("names")
    if isinstance(names, dict):
        try:
            return {int(k): str(v) for k, v in names.items()}
        except (TypeError, ValueError):
            return None
    if isinstance(names, list):
        return {i: str(v) for i, v in enumerate(names)}
    return None


def refresh_counts(root: Path) -> tuple[int, int, int]:
    return (count_images(root, "train"), count_images(root, "val"), count_images(root, "test"))
