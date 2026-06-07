"""Seed 3-class transition labels into the transition-classification-data twin and mine candidates.

For every frame, validated geometry (configs/papi_edny_transition.yaml) decides which tracked
lamps are inside their blend zone; those detection boxes are promoted from red/white -> class 2
(transition). Human-corrected red/white labels are otherwise authoritative (geometry never flips
red<->white). Only frames that gain >=1 transition box are rewritten, so every other label file
stays byte-identical to the Phase-1 original.

Each promoted box is recorded as a *candidate* (with temporal neighbours + colour features) for
the Phase 5 human spot-check. Colour/instability is cross-check signal only, never a label.

Run::

    .venv/Scripts/python workflows/scripts/build_transition_labels.py
    .venv/Scripts/python workflows/scripts/build_transition_labels.py --review-assets --review-max 300
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from _pipeline_utils import load_yaml
from papi.transition_labels import (
    CLASS_TRANSITION,
    Candidate,
    colour_features,
    lamp_geom_states,
    neighbour_states,
    track_state_sequences,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "papi_edny_transition.yaml"
REGIMES = ("daytime", "nighttime")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def process_video(video_dir: Path, airport_config: dict, *, want_colour: bool) -> tuple[list[Candidate], dict]:
    metadata = _read_csv(video_dir / "metadata.csv")
    tracks = _read_csv(video_dir / "tracks.csv")
    meta_by_file = {row["file"]: row for row in metadata}
    frames: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in tracks:
        frames[int(row["frame_index"])].append(row)
    seqs = track_state_sequences(tracks)

    candidates: list[Candidate] = []
    rewritten = 0
    per_lamp = Counter()
    bad_pose = 0

    for frame_index in sorted(frames):
        rows = frames[frame_index]
        file = rows[0]["file"]
        meta = meta_by_file.get(file)
        if meta is None:
            continue
        geom = lamp_geom_states(meta, airport_config)
        if not geom:
            bad_pose += 1
            continue

        new_classes: list[int] = []
        any_transition = False
        for row in rows:
            cls = int(row["class_id"])
            pid = row["physical_lamp_id"]
            if pid:
                lamp = geom.get(int(pid))
                if lamp is not None and lamp.state == "transition":
                    cls = CLASS_TRANSITION
                    any_transition = True
            new_classes.append(cls)
        if not any_transition:
            continue

        # Rewrite the frame's label file from tracks (6-decimal boxes; sub-pixel, negligible).
        label_path = video_dir / "labels" / (Path(file).stem + ".txt")
        label_path.write_text(
            "\n".join(
                f"{cls} {r['cx']} {r['cy']} {r['w']} {r['h']}"
                for r, cls in zip(rows, new_classes, strict=True)
            )
            + "\n",
            encoding="utf-8",
        )
        rewritten += 1

        image_bgr = None
        if want_colour:
            import cv2

            image_bgr = cv2.imread(str(video_dir / "images" / file))

        for row, cls in zip(rows, new_classes, strict=True):
            if cls != CLASS_TRANSITION:
                continue
            lamp = geom[int(row["physical_lamp_id"])]
            per_lamp[int(row["physical_lamp_id"])] += 1
            prev_s, next_s = neighbour_states(seqs.get(row["track_id"], []), frame_index)
            cf: dict = {}
            if image_bgr is not None:
                cf = colour_features(
                    image_bgr, (float(row["cx"]), float(row["cy"]), float(row["w"]), float(row["h"]))
                )
            candidates.append(
                Candidate(
                    source_id=video_dir.name, video_id=row["video_id"], frame_number=frame_index,
                    timestamp=meta.get("utc_exposure", ""), track_id=row["track_id"],
                    lamp_position=int(row["physical_lamp_id"]),
                    bbox=f"{row['cx']},{row['cy']},{row['w']},{row['h']}",
                    previous_state=prev_s, candidate_state="transition", next_state=next_s,
                    red_confidence="", white_confidence="", transition_score="",
                    colour_features=json.dumps(cf, separators=(",", ":")),
                    reason_for_flagging=(
                        f"geometric_blend_zone margin={lamp.margin_deg:.3f}deg "
                        f"elev={lamp.elevation_deg:.3f} set={lamp.set_angle_deg:.2f} "
                        f"prev={prev_s or '?'} next={next_s or '?'}"
                    ),
                    elevation_deg=lamp.elevation_deg, set_angle_deg=lamp.set_angle_deg,
                    margin_deg=lamp.margin_deg, runway=lamp.runway,
                    camera=meta.get("camera", ""), assignment_method=row.get("assignment_method", ""),
                    quality_flags=row.get("quality_flags", ""),
                )
            )

    summary = {
        "frames": len(frames),
        "transition_frames": rewritten,
        "transition_boxes": sum(per_lamp.values()),
        "per_lamp": dict(per_lamp),
        "frames_skipped_bad_pose": bad_pose,
    }
    return candidates, summary


def build(twin: Path, airport_config: dict, *, want_colour: bool) -> dict:
    all_candidates: list[Candidate] = []
    regimes: dict[str, dict] = {}
    for regime in REGIMES:
        regime_root = twin / regime
        if not regime_root.is_dir():
            continue
        videos: dict[str, dict] = {}
        for video_dir in sorted(p for p in regime_root.iterdir() if p.is_dir()):
            cands, summary = process_video(video_dir, airport_config, want_colour=want_colour)
            all_candidates.extend(cands)
            videos[video_dir.name] = summary
        regimes[regime] = videos

    # Write candidates CSV (sorted by smallest margin first = most boundary-confident).
    # candidate_id leads the row so the Phase 5 verification log can join on it.
    all_candidates.sort(key=lambda c: c.margin_deg)
    cand_path = twin / "transition_candidates.csv"
    with cand_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["candidate_id", *Candidate.fieldnames()])
        writer.writeheader()
        for cid, cand in enumerate(all_candidates, 1):
            writer.writerow({"candidate_id": f"cand_{cid:05d}", **cand.as_row()})

    manifest = {
        "twin": str(twin),
        "config": "papi_edny_transition.yaml",
        "total_candidates": len(all_candidates),
        "regimes": regimes,
        "per_lamp_total": dict(Counter(c.lamp_position for c in all_candidates)),
        "per_runway_total": dict(Counter(c.runway for c in all_candidates)),
        "candidates_csv": str(cand_path),
    }
    (twin / "transition_labels_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--no-colour", action="store_true", help="skip per-candidate colour features (faster)")
    args = parser.parse_args()

    airport_config = load_yaml(args.config)
    manifest = build(args.twin, airport_config, want_colour=not args.no_colour)

    print(json.dumps({
        "total_candidates": manifest["total_candidates"],
        "per_lamp_total": manifest["per_lamp_total"],
        "per_runway_total": manifest["per_runway_total"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
