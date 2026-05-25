"""Prepare a no-copy YOLO training config from the PAPI sequence dataset."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def prepare_sequence_dataset(dataset_root: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    splits: dict[str, list[str]] = {"train": [], "val": [], "test": []}

    for regime in ("daytime", "nighttime"):
        regime_root = dataset_root / regime
        for video_dir in sorted([path for path in regime_root.iterdir() if path.is_dir()]):
            with (video_dir / "metadata.csv").open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    split = row.get("split") or "train"
                    if split not in splits:
                        split = "train"
                    image_path = (regime_root / video_dir.name / row["image"]).resolve()
                    splits[split].append(image_path.as_posix())

    for split, entries in splits.items():
        (out_dir / f"{split}.txt").write_text("\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")

    data_path = out_dir.resolve().as_posix()
    (out_dir / "data.yaml").write_text(
        f"path: {data_path}\n"
        "train: train.txt\n"
        "val: val.txt\n"
        "test: test.txt\n"
        "names:\n"
        "  0: papi_light_red\n"
        "  1: papi_light_white\n",
        encoding="utf-8",
    )
    manifest = {
        "dataset_root": str(dataset_root),
        "out_dir": str(out_dir),
        "splits": {split: len(entries) for split, entries in splits.items()},
        "classes": {"0": "papi_light_red", "1": "papi_light_white"},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=REPO_ROOT / "data" / "datasets" / "papi_lamp_sequences",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "datasets" / "papi_lamp_sequences" / "yolo26n_combined",
    )
    args = parser.parse_args()
    manifest = prepare_sequence_dataset(args.dataset_root, args.out_dir)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
