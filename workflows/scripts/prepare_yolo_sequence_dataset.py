"""Prepare a no-copy YOLO training config from the PAPI sequence dataset."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


REGIMES = ("daytime", "nighttime")


def prepare_sequence_dataset(dataset_root: Path, out_dir: Path) -> dict:
    # Validate the input layout before creating out_dir or writing any config, so a
    # missing dataset fails cleanly instead of leaving a half-written output dir.
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")
    missing = [regime for regime in REGIMES if not (dataset_root / regime).is_dir()]
    if missing:
        raise FileNotFoundError(
            f"Dataset root {dataset_root} is missing required regime dir(s): {', '.join(missing)}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    splits: dict[str, list[str]] = {"train": [], "val": [], "test": []}

    for regime in REGIMES:
        regime_root = dataset_root / regime
        for video_dir in sorted([path for path in regime_root.iterdir() if path.is_dir()]):
            metadata_path = video_dir / "metadata.csv"
            if not metadata_path.exists():
                raise FileNotFoundError(f"Missing metadata.csv in sequence video dir: {metadata_path}")
            with metadata_path.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            if not rows:
                # A metadata.csv with only a header (no frames) contributes nothing;
                # skip it rather than crash on the empty-split set's .pop() below.
                continue

            # A sequence is one flight: all its frames must share a split, or near-identical
            # adjacent frames leak across train/val/test. Enforce one split per video rather
            # than trusting (and silently 'train'-defaulting) a per-row column (audit W2).
            raw_splits = {(row.get("split") or "").strip() or "train" for row in rows}
            unknown = raw_splits - set(splits)
            if unknown:
                raise ValueError(
                    f"{metadata_path} has unrecognised split value(s) {sorted(unknown)}; "
                    f"expected one of {sorted(splits)}"
                )
            if len(raw_splits) > 1:
                raise ValueError(
                    f"{metadata_path} mixes splits {sorted(raw_splits)}; all frames of a "
                    "sequence must share one split to avoid train/val leakage"
                )
            split = raw_splits.pop()

            for row in rows:
                image_name = row.get("image")
                if not image_name:
                    raise ValueError(f"metadata.csv row missing 'image' column in {metadata_path}")
                image_path = (regime_root / video_dir.name / image_name).resolve()
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
