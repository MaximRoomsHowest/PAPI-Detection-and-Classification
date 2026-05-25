#!/usr/bin/env python
"""Build matching image zips for normal-lens CVAT batches."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from prepare_yolo_seed import _source_from_flat_name

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BATCH_ROOT = REPO_ROOT / "data" / "cvat" / "normal_batches"
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"


def _resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def build_image_zips(batch_root: Path, raw_dir: Path) -> None:
    totals = {"batches": 0, "images": 0}

    for batch_dir in sorted(batch_root.glob("batch_*")):
        train_path = batch_dir / "train.txt"
        if not train_path.exists():
            continue

        entries = [line.strip() for line in train_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        zip_path = batch_dir / "images.zip"
        if zip_path.exists():
            zip_path.unlink()

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
            for entry in entries:
                flat_name = Path(entry).name
                src = _source_from_flat_name(flat_name, raw_dir)
                if not src.exists():
                    raise FileNotFoundError(f"Missing source image for {entry}: {src}")
                archive.write(src, entry.replace("\\", "/"))

        totals["batches"] += 1
        totals["images"] += len(entries)
        print(f"{batch_dir.name}: {len(entries)} images -> {zip_path}")

    print(f"Totals: {totals}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-root", type=Path, default=DEFAULT_BATCH_ROOT)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = parser.parse_args()

    build_image_zips(
        batch_root=_resolve_repo_path(args.batch_root),
        raw_dir=_resolve_repo_path(args.raw_dir),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
