"""Strict QA of transition-classification-data before training (Phase 6 gate).

Validates label format, class distribution, bbox bounds, duplicates, and — most importantly —
split integrity (no flight spans two splits => no adjacent-frame / source-video leakage). Reads
the per-flight split from each video's metadata.csv and the verified 3-class labels in the twin.
Writes docs/transition/dataset_qa_report.md and a JSON summary. Exits non-zero if a hard check
fails or transition examples are too few to train.

Run::

    .venv/Scripts/python workflows/scripts/prepare_transition_dataset.py
    .venv/Scripts/python workflows/scripts/qa_transition_dataset.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
REPORT = REPO_ROOT / "docs" / "transition" / "dataset_qa_report.md"
REGIMES = ("daytime", "nighttime")
CLASS_NAMES = {0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"}
MIN_TRANSITION_BOXES = 100  # below this, stop and report rather than pretend trainable
TEST_TRANSITION_FLOOR = 30  # below this, test transition metrics are statistically weak -> WARN


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _validate_label(path: Path) -> tuple[Counter, list[str]]:
    classes: Counter = Counter()
    errors: list[str] = []
    seen: set[str] = set()
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 5:
            errors.append(f"{path.name}:{i} expected 5 fields, got {len(parts)}")
            continue
        try:
            cls = int(parts[0])
            coords = [float(v) for v in parts[1:]]
        except ValueError:
            errors.append(f"{path.name}:{i} non-numeric field")
            continue
        if cls not in CLASS_NAMES:
            errors.append(f"{path.name}:{i} invalid class {cls}")
        if any(v < 0.0 or v > 1.0 for v in coords):
            errors.append(f"{path.name}:{i} coord outside [0,1]")
        if coords[2] <= 0 or coords[3] <= 0:
            errors.append(f"{path.name}:{i} non-positive w/h")
        if line.strip() in seen:
            errors.append(f"{path.name}:{i} duplicate box")
        seen.add(line.strip())
        classes[cls] += 1
    return classes, errors


def qa(twin: Path) -> dict:
    split_classes: dict[str, Counter] = defaultdict(Counter)
    split_frames: dict[str, int] = Counter()
    video_split: dict[str, set] = defaultdict(set)
    transition_by_video: Counter = Counter()
    split_regimes: dict[str, set] = defaultdict(set)
    orphans: Counter = Counter()  # images_without_labels / labels_without_images / metadata_without_labels
    errors: list[str] = []
    corrupt: list[str] = []
    total_frames = 0

    for regime in REGIMES:
        regime_root = twin / regime
        if not regime_root.is_dir():
            continue
        for video_dir in sorted(p for p in regime_root.iterdir() if p.is_dir()):
            meta = _read_csv(video_dir / "metadata.csv")
            split_of_file = {r["file"]: (r.get("split") or "train") for r in meta}
            for r in meta:
                split = r.get("split") or "train"
                video_split[video_dir.name].add(split)
                split_regimes[split].add(regime)
            # Orphan audit (both directions): a label with no image, an image with no
            # label, or a metadata row with no label file all signal a desynced flight.
            image_stems = {p.stem for p in (video_dir / "images").glob("*.JPG")} | {
                p.stem for p in (video_dir / "images").glob("*.jpg")
            }
            label_stems = {p.stem for p in (video_dir / "labels").glob("*.txt")}
            meta_stems = {Path(r["file"]).stem for r in meta}
            orphans["images_without_labels"] += len(image_stems - label_stems)
            orphans["labels_without_images"] += len(label_stems - image_stems)
            orphans["metadata_without_labels"] += len(meta_stems - label_stems)
            for label_path in sorted((video_dir / "labels").glob("*.txt")):
                total_frames += 1
                file = label_path.stem + ".JPG"
                if file not in split_of_file:
                    # Hard-error instead of silently bucketing into "train": a future
                    # flight with .jpg/.png filenames would otherwise make this report
                    # diverge from the real training split with no signal (audit WS-6a).
                    raise SystemExit(
                        f"QA: label {label_path} has no metadata row for '{file}' — "
                        "filename/extension mismatch between labels/ and metadata.csv."
                    )
                split = split_of_file[file]
                split_frames[split] += 1
                try:
                    classes, errs = _validate_label(label_path)
                except OSError:
                    corrupt.append(str(label_path))
                    continue
                errors.extend(errs)
                split_classes[split].update(classes)
                if classes.get(2, 0):
                    transition_by_video[video_dir.name] += classes[2]

    # split integrity: every flight entirely within one split
    leaking = {v: sorted(s) for v, s in video_split.items() if len(s) > 1}

    totals = Counter()
    for c in split_classes.values():
        totals.update(c)
    transition_total = totals.get(2, 0)
    red_total, white_total = totals.get(0, 0), totals.get(1, 0)

    # per-lamp transition (accepted) + exclusions from the verification log. Decisions other than
    # accepted_* are reverts to red/white (fallback_identity, telemetry_gap, stable_colour).
    per_lamp = Counter()
    excluded = 0
    excluded_by_reason: Counter = Counter()
    vlog = twin / "verification_log.csv"
    if vlog.exists():
        for r in _read_csv(vlog):
            if r["decision"].startswith("accepted"):
                per_lamp[r.get("track_id", "")] += 1
            else:
                excluded += 1
                excluded_by_reason[r["decision"]] += 1

    transition_in_train = split_classes.get("train", Counter()).get(2, 0)
    transition_in_val = split_classes.get("val", Counter()).get(2, 0)
    transition_in_test = split_classes.get("test", Counter()).get(2, 0)
    top_video, top_video_n = (transition_by_video.most_common(1) or [("", 0)])[0]
    overrep = top_video_n / transition_total if transition_total else 0.0

    # Soft warnings: surface real weaknesses (tiny/zero test transition support, a
    # regime trained-but-untested, file orphans) WITHOUT flipping a clean dataset to
    # NOT-ready — the gate keeps its existing hard criteria.
    warnings: list[str] = []
    if transition_in_test == 0:
        warnings.append("Test split has ZERO transition boxes — transition generalization is unmeasured.")
    elif transition_in_test < TEST_TRANSITION_FLOOR:
        warnings.append(
            f"Test split has only {transition_in_test} transition boxes (< {TEST_TRANSITION_FLOOR}); "
            "transition test metrics carry wide uncertainty."
        )
    missing_regimes = sorted(split_regimes.get("train", set()) - split_regimes.get("test", set()))
    if missing_regimes:
        warnings.append(
            f"Regime(s) in train but absent from test: {missing_regimes} — generalization to those is untested."
        )
    if sum(orphans.values()):
        warnings.append(f"Image/label/metadata orphans: {dict(orphans)} (a label has no image, or vice versa).")

    hard_fail = bool(leaking) or bool(corrupt) or transition_total < MIN_TRANSITION_BOXES
    ready = (not hard_fail) and transition_in_train > 0 and transition_in_val > 0 and not errors

    summary = {
        "total_frames": total_frames,
        "boxes": {"red": red_total, "white": white_total, "transition": transition_total},
        "transition_pct_of_boxes": round(100 * transition_total / max(1, red_total + white_total + transition_total), 2),
        "imbalance_red_white_to_transition": round((red_total + white_total) / max(1, transition_total), 1),
        "split_frames": dict(split_frames),
        "transition_by_split": {"train": transition_in_train, "val": transition_in_val, "test": transition_in_test},
        "transition_by_video": dict(transition_by_video),
        "most_loaded_clip_share": round(overrep, 3),
        "per_lamp_transition": dict(per_lamp),
        "excluded_from_transition": excluded,
        "excluded_by_reason": dict(excluded_by_reason),
        "format_errors": len(errors),
        "corrupt_files": len(corrupt),
        "split_leakage_flights": leaking,
        "orphans": dict(orphans),
        "split_regimes": {k: sorted(v) for k, v in split_regimes.items()},
        "warnings": warnings,
        "min_transition_required": MIN_TRANSITION_BOXES,
        "ready_for_training": ready,
        "hard_fail": hard_fail,
    }
    _write_report(summary, errors[:20])
    return summary


def _write_report(s: dict, sample_errors: list[str]) -> None:
    b = s["boxes"]
    lines = [
        "# Phase 6 — Dataset QA Report (`transition-classification-data`)",
        "",
        "Generated by `workflows/scripts/qa_transition_dataset.py`. Gate before training.",
        "",
        "## Counts",
        "",
        f"- Total frames (label files): **{s['total_frames']}**",
        f"- Boxes — red: **{b['red']}**, white: **{b['white']}**, transition: **{b['transition']}**",
        f"- Transition share of boxes: **{s['transition_pct_of_boxes']}%** "
        f"(imbalance red+white : transition ≈ **{s['imbalance_red_white_to_transition']} : 1**)",
        f"- Candidates excluded from transition (reverted to red/white): **{s['excluded_from_transition']}** "
        f"{json.dumps(s['excluded_by_reason'])}",
        "",
        "## Split distribution (flight-level)",
        "",
        f"- Frames per split: {json.dumps(s['split_frames'])}",
        f"- Transition boxes per split: {json.dumps(s['transition_by_split'])}",
        "",
        "## Leakage checks",
        "",
        f"- **Flights spanning >1 split (must be empty): {json.dumps(s['split_leakage_flights']) or '{}'}**",
        "- Adjacent-frame / source-video leakage: prevented by construction — one split per flight "
        "(audit W2 rule, reused from `prepare_yolo_sequence_dataset`).",
        f"- Most-loaded clip share of transitions: **{s['most_loaded_clip_share']}** "
        "(closer to 1.0 = one clip dominates).",
        "",
        "## Per-lamp transition distribution (accepted)",
        "",
        f"- {json.dumps(s['per_lamp_transition'])}",
        "",
        "## Validity",
        "",
        f"- Format errors: **{s['format_errors']}**, corrupt files: **{s['corrupt_files']}**",
    ]
    if sample_errors:
        lines += ["", "Sample errors:", "", *[f"- `{e}`" for e in sample_errors]]
    if s.get("warnings"):
        lines += ["", "## Warnings (non-blocking)", "", *[f"- ⚠ {w}" for w in s["warnings"]]]
    lines += [
        "",
        "## Verdict",
        "",
        f"- Minimum transition boxes required: {s['min_transition_required']}; have: **{s['boxes']['transition']}**.",
        f"- Transition present in train (**{s['transition_by_split']['train']}**) and val "
        f"(**{s['transition_by_split']['val']}**).",
        f"- **Ready for training: {'YES' if s['ready_for_training'] else 'NO'}**"
        + ("" if not s["hard_fail"] else "  — HARD FAIL (see leakage/corrupt/too-few above)."),
        "",
        "## Known limitations",
        "",
        f"- Transition is a small minority class ({s['transition_pct_of_boxes']}% of boxes); "
        "Phase 7 handles imbalance via transition-frame oversampling + colour-safe "
        "augmentation (no hue/sat jitter).",
        "- rwy-06 transition angles use FAA defaults (commissioned set-angles pending); affects "
        "angle-binding, not the visual transition label.",
        "- Verification was an AI spot-check of 36/~150 flips + a dataset-wide rule; a fuller human "
        "/ CVAT pass can extend it (`transition_cvat_bundle.zip`).",
    ]
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    args = parser.parse_args()
    summary = qa(args.twin)
    print(json.dumps(summary, indent=2))
    # Gate on the full verdict: a dataset with label-format errors (or no transition
    # boxes in train/val) printed "Ready: NO" but still exited 0, so a scripted
    # pipeline would train on it anyway (audit WS-8).
    return 0 if summary["ready_for_training"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
