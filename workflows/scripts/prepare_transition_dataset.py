"""Build the no-copy 3-class YOLO training config for transition-classification-data.

Reuses ``prepare_yolo_sequence_dataset.prepare_sequence_dataset`` for the split logic (which
already enforces one-split-per-flight, audit W2), then rewrites data.yaml + manifest to the
3-class taxonomy. Images resolve to the twin's hardlinks; labels resolve via /images/->/labels/
to the twin's verified 3-class labels.

Run::

    .venv/Scripts/python workflows/scripts/prepare_transition_dataset.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from prepare_yolo_sequence_dataset import prepare_sequence_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
CLASS_NAMES = {0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"}


def prepare(twin: Path, out_dir: Path) -> dict:
    manifest = prepare_sequence_dataset(twin, out_dir)
    data_path = out_dir.resolve().as_posix()
    (out_dir / "data.yaml").write_text(
        f"path: {data_path}\ntrain: train.txt\nval: val.txt\ntest: test.txt\nnames:\n"
        + "".join(f"  {i}: {CLASS_NAMES[i]}\n" for i in sorted(CLASS_NAMES)),
        encoding="utf-8",
    )
    manifest["classes"] = {str(i): CLASS_NAMES[i] for i in sorted(CLASS_NAMES)}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_TWIN / "transition_combined")
    args = parser.parse_args()
    print(json.dumps(prepare(args.twin, args.out_dir), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
