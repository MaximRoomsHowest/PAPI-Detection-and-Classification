"""Build a 2-class (red/white) TEST-split eval view over the transition twin.

The original 2-class sequence dataset is not present on this machine, but the
transition twin carries the same frames and the same human-corrected red/white
boxes — its only divergence is the 250 boxes relabeled class 2 (transition).
For evaluating the 2-class SERVING models on the held-out test split, this
script derives an equivalent 2-class view:

* images are HARD-LINKED (same NTFS volume, zero copy cost) into
  ``<twin>/redwhite_test_view/<video>/images``;
* labels are copied with every class-2 line mapped BACK to the lamp's original
  red/white class from ``tracks.csv`` (exact bbox-string match — the label lines
  were generated from those very rows, so the join is lossless; unmatched
  class-2 lines hard-error rather than guess);
* ``data.yaml`` + ``test.txt`` cover the full test split, and one
  ``data_<flight>.yaml`` per test flight enables the per-regime breakdown
  (the three test flights ARE the three regimes: 1000 m day wide,
  300 m day zoom, 500 m night wide — configs/split.yaml).

Run::

    .venv/Scripts/python workflows/scripts/build_redwhite_test_view.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
REGIMES = ("daytime", "nighttime")
VIEW_DIR_NAME = "redwhite_test_view"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build(twin: Path) -> dict:
    view_root = twin / VIEW_DIR_NAME
    view_root.mkdir(exist_ok=True)

    test_images: list[str] = []
    per_flight: dict[str, list[str]] = defaultdict(list)
    mapped_back = 0

    for regime in REGIMES:
        regime_root = twin / regime
        if not regime_root.is_dir():
            continue
        for video_dir in sorted(p for p in regime_root.iterdir() if p.is_dir()):
            meta = _read_csv(video_dir / "metadata.csv")
            test_files = [r["file"] for r in meta if (r.get("split") or "").strip() == "test"]
            if not test_files:
                continue
            tracks = _read_csv(video_dir / "tracks.csv")
            # (file, "cx cy w h") -> original class string; the label lines were
            # written from these rows so string equality is exact.
            original_class: dict[tuple[str, str], str] = {
                (r["file"], f"{r['cx']} {r['cy']} {r['w']} {r['h']}"): r["class_id"]
                for r in tracks
            }

            out_video = view_root / video_dir.name
            (out_video / "images").mkdir(parents=True, exist_ok=True)
            (out_video / "labels").mkdir(parents=True, exist_ok=True)

            for file in test_files:
                src_img = video_dir / "images" / file
                if not src_img.is_file():
                    raise SystemExit(f"missing test image: {src_img}")
                dst_img = out_video / "images" / file
                if not dst_img.exists():
                    os.link(src_img, dst_img)  # hardlink: zero-copy, same volume

                label_name = Path(file).stem + ".txt"
                src_label = video_dir / "labels" / label_name
                lines_out: list[str] = []
                for line in src_label.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    cls, rest = line.split(" ", 1)
                    if cls == "2":
                        key = (file, rest)
                        if key not in original_class:
                            raise SystemExit(
                                f"class-2 box in {src_label} has no tracks.csv row "
                                f"(bbox '{rest}') — refusing to guess its colour."
                            )
                        cls = original_class[key]
                        mapped_back += 1
                    lines_out.append(f"{cls} {rest}")
                (out_video / "labels" / label_name).write_text(
                    "\n".join(lines_out) + "\n", encoding="utf-8"
                )

                img_path = str(dst_img.resolve()).replace("\\", "/")
                test_images.append(img_path)
                per_flight[video_dir.name].append(img_path)

    if not test_images:
        raise SystemExit("no test-split frames found in the twin")

    (view_root / "test.txt").write_text("\n".join(test_images) + "\n", encoding="utf-8")
    yaml_names = "names:\n  0: papi_light_red\n  1: papi_light_white\n"
    root_line = f"path: {str(view_root.resolve()).replace(chr(92), '/')}\n"
    (view_root / "data.yaml").write_text(
        root_line + "train: test.txt\nval: test.txt\ntest: test.txt\n" + yaml_names,
        encoding="utf-8",
    )
    for flight, images in per_flight.items():
        list_name = f"test_{flight}.txt"
        (view_root / list_name).write_text("\n".join(images) + "\n", encoding="utf-8")
        (view_root / f"data_{flight}.yaml").write_text(
            root_line + f"train: {list_name}\nval: {list_name}\ntest: {list_name}\n" + yaml_names,
            encoding="utf-8",
        )

    summary = {
        "view_root": str(view_root),
        "test_frames": len(test_images),
        "class2_boxes_mapped_back": mapped_back,
        "flights": {flight: len(images) for flight, images in sorted(per_flight.items())},
    }
    (view_root / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    args = parser.parse_args()
    print(json.dumps(build(args.twin), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
