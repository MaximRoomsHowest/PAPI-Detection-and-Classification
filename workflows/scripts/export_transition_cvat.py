"""Export the verified transition frames as a CVAT-importable Ultralytics YOLO 1.0 bundle.

Reuses packages/papi/src/papi/cvat_export.zip_bundle. Produces the 3-class layout CVAT's
"Ultralytics YOLO Detection 1.0" importer expects (data.yaml + labels/{train,val} + train.txt/
val.txt), defaulting to annotations-only (small; upload onto an existing CVAT task) with
--with-images to include the frames. Train/val split follows the flight-level metadata split.

Run::

    .venv/Scripts/python workflows/scripts/export_transition_cvat.py
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

from papi.cvat_export import zip_bundle

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
REGIMES = ("daytime", "nighttime")
CLASS_NAMES = {0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _has_transition(label_path: Path) -> bool:
    return label_path.exists() and any(
        line.startswith("2 ") for line in label_path.read_text(encoding="utf-8").splitlines()
    )


def export(twin: Path, out_dir: Path, *, with_images: bool) -> dict:
    for sub in ("train", "val"):
        (out_dir / "labels" / sub).mkdir(parents=True, exist_ok=True)
        if with_images:
            (out_dir / "images" / sub).mkdir(parents=True, exist_ok=True)
    subsets: dict[str, list[str]] = {"train": [], "val": []}
    counts = {"train": 0, "val": 0}

    for regime in REGIMES:
        regime_root = twin / regime
        if not regime_root.is_dir():
            continue
        for video_dir in sorted(p for p in regime_root.iterdir() if p.is_dir()):
            split_by_file = {r["file"]: (r.get("split") or "train") for r in _read_csv(video_dir / "metadata.csv")}
            for label_path in sorted((video_dir / "labels").glob("*.txt")):
                if not _has_transition(label_path):
                    continue
                file = label_path.stem + ".JPG"
                subset = "val" if split_by_file.get(file, "train") in ("val", "test") else "train"
                flat = f"{video_dir.name}__{label_path.stem}"
                shutil.copy2(label_path, out_dir / "labels" / subset / f"{flat}.txt")
                if with_images:
                    src_img = video_dir / "images" / file
                    if src_img.exists():
                        shutil.copy2(src_img, out_dir / "images" / subset / f"{flat}.JPG")
                subsets[subset].append(f"./images/{subset}/{flat}.JPG")
                counts[subset] += 1

    for subset, lines in subsets.items():
        (out_dir / f"{subset}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    (out_dir / "data.yaml").write_text(
        "path: ./\ntrain: train.txt\nval: val.txt\nnames:\n"
        + "".join(f"  {i}: {CLASS_NAMES[i]}\n" for i in sorted(CLASS_NAMES)),
        encoding="utf-8",
    )
    zip_path = zip_bundle(out_dir, out_dir.parent / "transition_cvat_bundle.zip")
    return {"counts": counts, "with_images": with_images, "data_yaml": str(out_dir / "data.yaml"), "zip": str(zip_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_TWIN / "cvat_bundle")
    parser.add_argument("--with-images", action="store_true")
    args = parser.parse_args()
    import json

    print(json.dumps(export(args.twin, args.out_dir, with_images=args.with_images), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
