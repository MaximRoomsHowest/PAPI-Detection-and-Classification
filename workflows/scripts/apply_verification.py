"""Apply Phase 5 verification verdicts to the twin and write the verification log.

Verdicts come from a visual spot-check of per-flip montages (review_assets/review_page_*.png,
36 flips across all strata). The review established an evidence-based rule, applied dataset-wide:

* ``fallback_identity`` (left-to-right lamp id on zoom/mirrored geometry) -> ``ambiguous_review``:
  identity unreliable, the "flip" may be a tracking artifact -> revert that box to its original
  red/white label (excluded from the transition class).
* ``elev_discontinuity`` -> ``accepted_transition`` with note ``angle_unreliable``: the visual
  red<->white change is genuine; only the telemetry angle at the flip is untrustworthy.
* otherwise -> ``accepted_transition`` (flip-anchored + colour-confirmed).

Reverting rewrites only the affected lamp's class back to the human red/white label from
tracks.csv; accepted boxes keep class 2. Writes verification_log.csv (brief schema) and a summary.

Run::

    .venv/Scripts/python workflows/scripts/apply_verification.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
REGIMES = ("daytime", "nighttime")
CLASS_TRANSITION = 2
CLASS_STATE = {0: "red", 1: "white"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _video_dir(twin: Path, source_id: str) -> Path | None:
    for regime in REGIMES:
        d = twin / regime / source_id
        if d.is_dir():
            return d
    return None


def decide(review_flag: str) -> tuple[str, str]:
    if "fallback_identity" in review_flag:
        return "ambiguous_review", "unreliable left-to-right lamp identity (zoom/mirror); excluded from training"
    if "elev_discontinuity" in review_flag:
        return "accepted_transition", "visual transition genuine; angle_unreliable (telemetry discontinuity)"
    return "accepted_transition", "flip-anchored + colour-confirmed"


def apply(twin: Path) -> dict:
    candidates = _read_csv(twin / "transition_candidates_ranked.csv")
    reviewed_keys = set()
    sample_path = twin / "review_assets" / "review_sample_flips.csv"
    if sample_path.exists():
        for r in _read_csv(sample_path):
            reviewed_keys.add((r["source_id"], r["track_id"], int(r["flip_frame"])))

    # decision per candidate
    log_rows: list[dict[str, str]] = []
    accepted: set[tuple[str, int, str]] = set()  # (source, frame, track) kept as transition
    decisions = Counter()
    for c in candidates:
        decision, note = decide(c["review_flag"])
        if (c["source_id"], c["track_id"], int(c["flip_frame"])) in reviewed_keys:
            note += " [visually reviewed]"
        decisions[decision] += 1
        from_state, to_state = c["previous_state"], c["next_state"]
        # the box's original label = from_state if before the flip boundary else to_state
        old_label = from_state if int(c["frame_offset"]) <= 0 else to_state
        if decision == "accepted_transition":
            accepted.add((c["source_id"], int(c["frame_number"]), c["track_id"]))
            new_label = "transition"
        else:
            new_label = old_label
        log_rows.append({
            "candidate_id": c["candidate_id"], "decision": decision, "old_label": old_label,
            "new_label": new_label, "reviewer_note": note, "source_id": c["source_id"],
            "frame_number": c["frame_number"], "track_id": c["track_id"],
        })

    # rewrite affected label files: class 2 only for accepted boxes, else original tracks class
    affected_by_video: dict[str, set[int]] = defaultdict(set)
    for c in candidates:
        affected_by_video[c["source_id"]].add(int(c["frame_number"]))

    final_transition_boxes = 0
    for source_id, frames_set in affected_by_video.items():
        vd = _video_dir(twin, source_id)
        if vd is None:
            continue
        tracks = _read_csv(vd / "tracks.csv")
        by_frame: dict[int, list[dict[str, str]]] = defaultdict(list)
        for r in tracks:
            by_frame[int(r["frame_index"])].append(r)
        for fr in frames_set:
            rows = by_frame.get(fr, [])
            if not rows:
                continue
            file = rows[0]["file"]
            lines = []
            for r in rows:
                keep_transition = (source_id, fr, r["track_id"]) in accepted
                cls = CLASS_TRANSITION if keep_transition else int(r["class_id"])
                lines.append(f"{cls} {r['cx']} {r['cy']} {r['w']} {r['h']}")
            # Drop exact-duplicate boxes (pre-existing annotation artifacts in a few frames).
            lines = list(dict.fromkeys(lines))
            final_transition_boxes += sum(1 for ln in lines if ln.startswith("2 "))
            (vd / "labels" / (Path(file).stem + ".txt")).write_text("\n".join(lines) + "\n", encoding="utf-8")

    log_path = twin / "verification_log.csv"
    with log_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(log_rows[0].keys()))
        writer.writeheader()
        writer.writerows(log_rows)

    summary = {
        "candidates": len(candidates),
        "flips_visually_reviewed": len(reviewed_keys),
        "decisions": dict(decisions),
        "final_transition_boxes": final_transition_boxes,
        "verification_log": str(log_path),
    }
    (twin / "verification_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    args = parser.parse_args()
    print(json.dumps(apply(args.twin), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
