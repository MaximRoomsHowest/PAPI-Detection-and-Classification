"""Safely duplicate the PAPI sequence dataset into ``transition-classification-data``.

The original dataset (``data/datasets/papi_lamp_sequences`` — in practice the populated
copy under ``PAPI-artifacts/.../papi_lamp_sequences``) must never be modified. This script
builds a structural twin in which:

* **images are HARDLINKED** — same NTFS volume, so each duplicated frame is a real
  directory entry (file counts match the original) but consumes no extra bytes, and the
  original file content is never written. Ultralytics resolves a label from an image path
  by swapping ``/images/`` -> ``/labels/``; hardlinking the images *into* the twin lets the
  twin carry its own (later 3-class) labels without touching the source tree.
* **labels are real copies** — Phase 3 rewrites these in place to the 3-class taxonomy, so
  they must be independent files, not hardlinks back into the original.
* **per-video CSVs + top-level manifests are real copies** — small, and Phase 3/6 annotate
  them.

The derived ``yolo26n_combined`` no-copy config is intentionally NOT duplicated: it is a
generated training config (with absolute paths), regenerated fresh for 3-class in Phase 3.

Run::

    .venv/Scripts/python workflows/scripts/duplicate_transition_dataset.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# The populated canonical dataset lives in the sibling artifacts snapshot — a
# machine-specific location, so there is no portable hardcoded default. Set
# PAPI_ARTIFACTS_ROOT to the artifacts checkout (the snapshot-relative path is
# appended) or pass --source explicitly.
_ARTIFACTS_ROOT = os.environ.get("PAPI_ARTIFACTS_ROOT")
DEFAULT_SOURCE = (
    Path(_ARTIFACTS_ROOT) / "2026-05-26-cleanup" / "data" / "datasets" / "papi_lamp_sequences"
    if _ARTIFACTS_ROOT
    else None
)
DEFAULT_TARGET = REPO_ROOT / "data" / "datasets" / "transition-classification-data"

REGIMES = ("daytime", "nighttime")
TOP_LEVEL_FILES = ("manifest.json", "tracking_manifest.json", "validation_summary.json")
PER_VIDEO_COPY = ("metadata.csv", "tracks.csv", "transitions.csv")
# desktop.ini is Windows shell metadata; labels.cache is an Ultralytics binary cache that
# would go stale the moment Phase 3 rewrites a label — let Ultralytics rebuild it.
SKIP_NAMES = {"desktop.ini", "labels.cache", "Thumbs.db"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def _hardlink(src: Path, dst: Path, *, overwrite: bool) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if not overwrite:
            return "skipped"
        dst.unlink()
    os.link(src, dst)  # NTFS hardlink; raises if cross-volume
    return "linked"


def _copy(src: Path, dst: Path, *, overwrite: bool) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and not overwrite:
        return "skipped"
    shutil.copy2(src, dst)
    return "copied"


def _tree_signature(root: Path) -> dict[str, int]:
    """Cheap (count, total_bytes) signature used to prove the source is untouched."""
    images = labels = csvs = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        total_bytes += path.stat().st_size
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            images += 1
        elif suffix == ".txt" and path.parent.name == "labels":
            labels += 1
        elif suffix == ".csv":
            csvs += 1
    return {"images": images, "labels": labels, "csv": csvs, "total_bytes": total_bytes}


def duplicate(source: Path, target: Path, *, overwrite: bool) -> dict:
    if not source.is_dir():
        raise FileNotFoundError(f"Source dataset not found: {source}")
    missing = [r for r in REGIMES if not (source / r).is_dir()]
    if missing:
        raise FileNotFoundError(f"Source {source} missing regime dir(s): {', '.join(missing)}")

    target.mkdir(parents=True, exist_ok=True)
    actions = {"linked": 0, "copied": 0, "skipped": 0}
    regimes: dict[str, dict] = {}

    for regime in REGIMES:
        regime_src = source / regime
        regime_videos: dict[str, dict] = {}
        for video_dir in sorted(p for p in regime_src.iterdir() if p.is_dir()):
            dst_video = target / regime / video_dir.name
            counts = {"images": 0, "labels": 0, "csv": 0}

            images_src = video_dir / "images"
            if images_src.is_dir():
                for img in sorted(images_src.iterdir()):
                    if not img.is_file() or img.name in SKIP_NAMES:
                        continue
                    if img.suffix.lower() not in IMAGE_SUFFIXES:
                        continue
                    actions[_hardlink(img, dst_video / "images" / img.name, overwrite=overwrite)] += 1
                    counts["images"] += 1

            labels_src = video_dir / "labels"
            if labels_src.is_dir():
                for lbl in sorted(labels_src.iterdir()):
                    if not lbl.is_file() or lbl.name in SKIP_NAMES or lbl.suffix.lower() != ".txt":
                        continue
                    actions[_copy(lbl, dst_video / "labels" / lbl.name, overwrite=overwrite)] += 1
                    counts["labels"] += 1

            for name in PER_VIDEO_COPY:
                src_file = video_dir / name
                if src_file.exists():
                    actions[_copy(src_file, dst_video / name, overwrite=overwrite)] += 1
                    counts["csv"] += 1

            regime_videos[video_dir.name] = counts
        regimes[regime] = {"videos": regime_videos}

    for name in TOP_LEVEL_FILES:
        src_file = source / name
        if src_file.exists():
            actions[_copy(src_file, target / name, overwrite=overwrite)] += 1

    return {"source": str(source), "target": str(target), "actions": actions, "regimes": regimes}


def verify(source: Path, target: Path) -> dict:
    src_sig = _tree_signature(source)
    tgt_sig = _tree_signature(target)
    checks = {
        "images_match": src_sig["images"] == tgt_sig["images"],
        "labels_match": src_sig["labels"] == tgt_sig["labels"],
        # The twin omits the derived yolo26n_combined config, so its CSV count can be <= source.
        "csv_present": tgt_sig["csv"] >= src_sig["csv"] - 3,
    }
    return {"source_signature": src_sig, "target_signature": tgt_sig, "checks": checks,
            "ok": all(checks.values())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--overwrite", action="store_true", help="relink/recopy existing files")
    args = parser.parse_args()
    if args.source is None:
        parser.error("set PAPI_ARTIFACTS_ROOT or pass --source <papi_lamp_sequences dir>")

    src_before = _tree_signature(args.source)
    report = duplicate(args.source, args.target, overwrite=args.overwrite)
    src_after = _tree_signature(args.source)
    report["original_unchanged"] = src_before == src_after
    report["verification"] = verify(args.source, args.target)

    (args.target / "_duplication_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "actions": report["actions"],
        "original_unchanged": report["original_unchanged"],
        "verification_ok": report["verification"]["ok"],
        "checks": report["verification"]["checks"],
        "target_signature": report["verification"]["target_signature"],
    }, indent=2))
    return 0 if report["original_unchanged"] and report["verification"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
