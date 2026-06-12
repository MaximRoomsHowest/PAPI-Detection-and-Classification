"""Seed flip-anchored 3-class transition labels into the twin and mine candidates.

Transitions are anchored to the authoritative red<->white flips in each video's transitions.csv
(derived from human-corrected labels). For each flip, the tracked lamp's box is promoted to
class 2 (transition) over a short +/-half_window frame window where it is visibly changing; all
other lamps and frames keep their human red/white labels. Geometry is used only to derive each
lamp's EMPIRICAL set-angle (median approach-elevation at its flips) and to flag flips with
discontinuous telemetry. See packages/papi/src/papi/transition_labels.py for why the earlier
geometric-blend-zone seeding was abandoned.

Run (reset labels first so no stale class-2 remains)::

    .venv/Scripts/python workflows/scripts/duplicate_transition_dataset.py --overwrite
    .venv/Scripts/python workflows/scripts/build_transition_labels.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from _pipeline_utils import load_yaml
from papi.transition_labels import (
    CLASS_TRANSITION,
    Candidate,
    approach_elevation_deg,
    colour_features,
    empirical_set_angle,
    parse_flips,
    window_frames,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
DEFAULT_CONFIG = REPO_ROOT / "configs" / "papi_edny_transition.yaml"
REGIMES = ("daytime", "nighttime")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def process_video(video_dir: Path, airport_config: dict, *, half_window: int, want_colour: bool):
    metadata = _read_csv(video_dir / "metadata.csv")
    tracks = _read_csv(video_dir / "tracks.csv")
    transitions_path = video_dir / "transitions.csv"
    transitions = _read_csv(transitions_path) if transitions_path.exists() else []

    meta_by_file = {row["file"]: row for row in metadata}
    meta_by_idx = {int(row["sequence_index"]): row for row in metadata}
    frames: dict[int, list[dict[str, str]]] = defaultdict(list)
    observed: dict[str, set[int]] = defaultdict(set)
    for row in tracks:
        fr = int(row["frame_index"])
        frames[fr].append(row)
        observed[row["track_id"]].add(fr)

    elev_cache: dict[int, float] = {}

    def elev(frame: int) -> float:
        if frame not in elev_cache:
            row = meta_by_idx.get(frame)
            elev_cache[frame] = approach_elevation_deg(row, airport_config)[1] if row else math.nan
        return elev_cache[frame]

    flips = parse_flips(transitions)

    # Empirical set-angle per lamp = median approach-elevation at its flip boundaries.
    set_angle_samples: dict[str, list[float]] = defaultdict(list)
    for flip in flips:
        mids = [e for e in (elev(flip.from_frame), elev(flip.to_frame)) if math.isfinite(e)]
        if mids:
            set_angle_samples[flip.lamp_position].append(statistics.mean(mids))
    set_angles = {lp: empirical_set_angle(v) for lp, v in set_angle_samples.items()}

    # Mark which (frame, track) boxes become transition.
    marked: dict[tuple[int, str], tuple] = {}
    for flip in flips:
        e_f, e_t = elev(flip.from_frame), elev(flip.to_frame)
        disc = "elev_discontinuity" if (math.isfinite(e_f) and math.isfinite(e_t) and abs(e_f - e_t) > 0.5) else ""
        for fr in window_frames(flip, half_window, observed.get(flip.track_id, set())):
            marked[(fr, flip.track_id)] = (flip, fr - flip.from_frame, disc)

    candidates: list[Candidate] = []
    per_lamp = Counter()
    affected = sorted({fr for (fr, _t) in marked})
    for fr in affected:
        rows = frames[fr]
        file = rows[0]["file"]
        meta = meta_by_file.get(file, {})
        new_classes = [
            CLASS_TRANSITION if (fr, r["track_id"]) in marked else int(r["class_id"]) for r in rows
        ]
        label_path = video_dir / "labels" / (Path(file).stem + ".txt")
        # dict.fromkeys drops exact-duplicate boxes (pre-existing annotation artifacts).
        label_lines = list(dict.fromkeys(
            f"{cls} {r['cx']} {r['cy']} {r['w']} {r['h']}"
            for r, cls in zip(rows, new_classes, strict=True)
        ))
        label_path.write_text("\n".join(label_lines) + "\n", encoding="utf-8")

        image_bgr = None
        if want_colour:
            import cv2

            image_bgr = cv2.imread(str(video_dir / "images" / file))

        for row, cls in zip(rows, new_classes, strict=True):
            if cls != CLASS_TRANSITION:
                continue
            flip, offset, disc = marked[(fr, row["track_id"])]
            per_lamp[row["physical_lamp_id"]] += 1
            cf = colour_features(
                image_bgr, (float(row["cx"]), float(row["cy"]), float(row["w"]), float(row["h"]))
            ) if image_bgr is not None else {}
            sa = set_angles.get(flip.lamp_position)
            quality = ";".join(f for f in (row.get("quality_flags", ""), disc) if f)
            candidates.append(
                Candidate(
                    source_id=video_dir.name, video_id=row["video_id"], frame_number=fr,
                    timestamp=meta.get("utc_exposure", ""), track_id=row["track_id"],
                    lamp_position=row["physical_lamp_id"],
                    bbox=f"{row['cx']},{row['cy']},{row['w']},{row['h']}",
                    previous_state=flip.from_state, candidate_state="transition",
                    next_state=flip.to_state, transition_type=flip.transition_type,
                    flip_frame=flip.from_frame, frame_offset=offset,
                    approach_elevation_deg=elev(fr),  # NaN when missing; as_row emits "" (LS-9)
                    empirical_set_angle_deg=f"{sa:.3f}" if sa is not None else "",
                    runway=approach_elevation_deg(meta, airport_config)[0] if meta else "",
                    camera=meta.get("camera", ""),
                    colour_features=json.dumps(cf, separators=(",", ":")),
                    transition_score="",
                    reason_for_flagging=(
                        f"flip_anchored type={flip.transition_type} offset={offset:+d} "
                        f"prev={flip.from_state} next={flip.to_state}"
                        + (f" [{disc}]" if disc else "")
                    ),
                    quality_flags=quality,
                )
            )

    summary = {
        "frames": len(frames),
        "flips": len(flips),
        "transition_boxes": sum(per_lamp.values()),
        "transition_frames": len(affected),
        "per_lamp": dict(per_lamp),
        "empirical_set_angle_deg": {lp: round(v, 3) for lp, v in set_angles.items() if v is not None},
    }
    return candidates, summary


def build(twin: Path, airport_config: dict, *, half_window: int, want_colour: bool) -> dict:
    all_candidates: list[Candidate] = []
    regimes: dict[str, dict] = {}
    set_angle_by_lamp: dict[str, list[float]] = defaultdict(list)
    for regime in REGIMES:
        regime_root = twin / regime
        if not regime_root.is_dir():
            continue
        videos: dict[str, dict] = {}
        for video_dir in sorted(p for p in regime_root.iterdir() if p.is_dir()):
            cands, summary = process_video(
                video_dir, airport_config, half_window=half_window, want_colour=want_colour
            )
            all_candidates.extend(cands)
            videos[video_dir.name] = summary
            for lp, v in summary["empirical_set_angle_deg"].items():
                if lp:
                    set_angle_by_lamp[lp].append(v)
        regimes[regime] = videos

    all_candidates.sort(key=lambda c: (c.source_id, c.track_id, c.frame_number))
    cand_path = twin / "transition_candidates.csv"
    with cand_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=Candidate.fieldnames())
        writer.writeheader()
        for cid, cand in enumerate(all_candidates, 1):
            writer.writerow(cand.as_row(f"cand_{cid:05d}"))

    manifest = {
        "twin": str(twin), "config": "papi_edny_transition.yaml", "half_window": half_window,
        "total_candidates": len(all_candidates),
        "per_lamp_total": dict(Counter(c.lamp_position for c in all_candidates)),
        "per_runway_total": dict(Counter(c.runway for c in all_candidates)),
        "per_type_total": dict(Counter(c.transition_type for c in all_candidates)),
        "empirical_set_angle_by_lamp_deg": {
            lp: round(statistics.median(v), 3) for lp, v in sorted(set_angle_by_lamp.items())
        },
        "regimes": regimes,
    }
    (twin / "transition_labels_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--half-window", type=int, default=2, help="frames each side of a flip to seed")
    parser.add_argument("--no-colour", action="store_true")
    args = parser.parse_args()

    airport_config = load_yaml(args.config)
    manifest = build(args.twin, airport_config, half_window=args.half_window, want_colour=not args.no_colour)
    print(json.dumps({
        "total_candidates": manifest["total_candidates"],
        "per_type_total": manifest["per_type_total"],
        "per_lamp_total": manifest["per_lamp_total"],
        "empirical_set_angle_by_lamp_deg": manifest["empirical_set_angle_by_lamp_deg"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
