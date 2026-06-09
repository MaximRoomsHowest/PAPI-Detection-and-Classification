"""Manual-review triage of the flip-anchored transition labels (audit, 2026-06-09).

Quantifies how many class-2 (transition) boxes are actually *stable* red/white by reusing the exact
colour verdict the label gate uses (``papi.transition_scoring.classify_lamp_colour``), attributes
each suspected mislabel to a root cause, and extracts the suspect lamp crops into a browsable folder
+ contact sheet so they can be eyeballed directly (full 20MP frames are useless -- the lamp is a few
dozen px and the overlay text covers it).

Root-cause buckets (same policy apply_verification now enforces):
  * ``fallback_identity``  -- left-to-right lamp id unreliable (already excluded pre-fix).
  * ``telemetry_gap``      -- ``elev_discontinuity``: the flip window does not bracket a captured
                              colour change (real flip in an unsampled gap); both sides are stable.
  * ``stable_red`` / ``stable_white`` -- window-edge colour bleed: crop is a pure stable colour.

"currently_transition" reflects the PRE-FIX labels (old apply_verification excluded only
fallback_identity), so the report states how many of the live training boxes are mislabelled.

Read-only over the dataset (writes only under ``<twin>/label_review/``). Run::

    .venv/Scripts/python workflows/scripts/review_transition_labels.py
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from papi.transition_scoring import classify_lamp_colour
from papi.transition_scoring import review_flag as compute_review_flag

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
REGIMES = ("daytime", "nighttime")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _video_dir(twin: Path, source_id: str) -> Path | None:
    for regime in REGIMES:
        d = twin / regime / source_id
        if d.is_dir():
            return d
    return None


def new_exclusion(review_flag: str, verdict: str) -> str:
    """Root-cause bucket the fixed gate assigns (``""`` = kept as a genuine transition)."""
    if "fallback_identity" in review_flag:
        return "fallback_identity"
    if "elev_discontinuity" in review_flag:
        return "telemetry_gap"
    if verdict in ("red", "white"):
        return f"stable_{verdict}"
    return ""


def _rows_with_verdicts(twin: Path) -> list[dict]:
    ranked = twin / "transition_candidates_ranked.csv"
    src = ranked if ranked.exists() else twin / "transition_candidates.csv"
    out = []
    for r in _read_csv(src):
        try:
            colour = json.loads(r.get("colour_features") or "{}")
        except json.JSONDecodeError:
            colour = {}
        verdict = r.get("colour_verdict") or classify_lamp_colour(colour)
        flag = r.get("review_flag")
        if flag is None:  # candidates.csv has no review_flag column -> derive it
            flag = compute_review_flag(r.get("quality_flags", ""), r.get("runway", ""))
        # PRE-FIX labels: old apply_verification kept everything except fallback_identity.
        currently_transition = "fallback_identity" not in flag
        out.append({
            **r, "colour": colour, "colour_verdict": verdict, "review_flag": flag,
            "currently_transition": currently_transition,
            "new_exclusion": new_exclusion(flag, verdict),
        })
    return out


def summarize(rows: list[dict]) -> dict:
    live = [r for r in rows if r["currently_transition"]]
    mislabelled = [r for r in live if r["new_exclusion"]]
    by_offset = defaultdict(Counter)
    for r in live:
        by_offset[int(r["frame_offset"])][r["new_exclusion"] or "kept_transition"] += 1
    return {
        "total_candidates": len(rows),
        "currently_labelled_transition": len(live),
        "verdict_breakdown_live": dict(Counter(r["colour_verdict"] for r in live)),
        "mislabelled_count": len(mislabelled),
        "mislabelled_pct_of_live": round(100 * len(mislabelled) / max(1, len(live)), 1),
        "mislabel_reason_breakdown": dict(Counter(r["new_exclusion"] for r in mislabelled)),
        "kept_after_fix": len(live) - len(mislabelled),
        "by_frame_offset": {str(k): dict(v) for k, v in sorted(by_offset.items())},
    }


def write_triage(rows: list[dict], out_dir: Path) -> Path:
    cols = ["candidate_id", "source_id", "frame_number", "track_id", "lamp_position",
            "frame_offset", "transition_type", "review_flag", "colour_verdict",
            "currently_transition", "new_exclusion", "red_ratio", "orange_amber_ratio",
            "white_ratio", "val_mean", "approach_elevation_deg", "timestamp"]
    path = out_dir / "transition_label_triage.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            c = r["colour"]
            w.writerow({
                "candidate_id": r.get("candidate_id", ""), "source_id": r["source_id"],
                "frame_number": r["frame_number"], "track_id": r["track_id"],
                "lamp_position": r.get("lamp_position", ""), "frame_offset": r["frame_offset"],
                "transition_type": r.get("transition_type", ""), "review_flag": r["review_flag"],
                "colour_verdict": r["colour_verdict"], "currently_transition": r["currently_transition"],
                "new_exclusion": r["new_exclusion"],
                "red_ratio": round(float(c.get("red_ratio", 0.0)), 3),
                "orange_amber_ratio": round(float(c.get("orange_amber_ratio", 0.0)), 3),
                "white_ratio": round(float(c.get("white_ratio", 0.0)), 3),
                "val_mean": round(float(c.get("val_mean", 0.0)), 1),
                "approach_elevation_deg": r.get("approach_elevation_deg", ""),
                "timestamp": r.get("timestamp", ""),
            })
    return path


def _crop(img, bbox: str, pad: float = 1.5):
    import numpy as np  # noqa: F401  (cv2 returns ndarrays)

    cx, cy, bw, bh = (float(v) for v in bbox.split(","))
    h_img, w_img = img.shape[:2]
    side = max(bw, bh) * (1 + 2 * pad)
    x1 = max(0, int((cx - side / 2) * w_img))
    x2 = min(w_img, int((cx + side / 2) * w_img))
    y1 = max(0, int((cy - side / 2) * h_img))
    y2 = min(h_img, int((cy + side / 2) * h_img))
    crop = img[y1:y2, x1:x2]
    return crop if crop.size else None


def extract_crops(rows: list[dict], twin: Path, out_dir: Path, per_reason: int = 64) -> dict:
    import cv2

    suspects = [r for r in rows if r["currently_transition"] and r["new_exclusion"]]
    # Group by (source, frame) so each 20MP frame is decoded exactly once and released before the
    # next -- caching every unique frame OOMs (each decodes to ~60MB).
    by_source_frame: dict[str, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in suspects:
        by_source_frame[r["source_id"]][int(r["frame_number"])].append(r)

    tiles: dict[str, list] = defaultdict(list)
    saved = Counter()
    for source_id, frames in by_source_frame.items():
        vd = _video_dir(twin, source_id)
        if vd is None:
            continue
        frame_to_file = {int(t["frame_index"]): t["file"] for t in _read_csv(vd / "tracks.csv")}
        for fr, group in sorted(frames.items()):
            file = frame_to_file.get(fr)
            if not file:
                continue
            img = cv2.imread(str(vd / "images" / file))
            if img is None:
                continue
            for r in group:
                crop = _crop(img, r["bbox"])
                if crop is None:
                    continue
                reason = r["new_exclusion"]
                tile = cv2.resize(crop, (128, 128), interpolation=cv2.INTER_NEAREST)
                c = r["colour"]
                cap = f"{r.get('candidate_id','')} {r['colour_verdict']} o{r['frame_offset']}"
                sub = f"r{float(c.get('red_ratio',0)):.2f} a{float(c.get('orange_amber_ratio',0)):.2f} w{float(c.get('white_ratio',0)):.2f}"
                d = out_dir / "suspect_crops" / reason
                d.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(d / f"{r.get('candidate_id','x')}_{source_id}_{fr}.png"), tile)
                saved[reason] += 1
                if len(tiles[reason]) < per_reason:
                    tiles[reason].append((tile, cap, sub))
            img = None  # release the 20MP frame before decoding the next

    montages = {}
    for reason, items in tiles.items():
        montage = _montage(items)
        if montage is not None:
            mp = out_dir / f"montage_{reason}.png"
            cv2.imwrite(str(mp), montage)
            montages[reason] = str(mp)
    return {"crops_saved": dict(saved), "montages": montages}


def _montage(items: list, cols: int = 8):
    import cv2
    import numpy as np

    if not items:
        return None
    cell_w, cell_h, pad = 128, 128 + 30, 4  # 30px caption strip under each tile
    rows_n = (len(items) + cols - 1) // cols
    canvas = np.full(((cell_h + pad) * rows_n + pad, (cell_w + pad) * cols + pad, 3), 30, np.uint8)
    for i, (tile, cap, sub) in enumerate(items):
        r, ccol = divmod(i, cols)
        x = pad + ccol * (cell_w + pad)
        y = pad + r * (cell_h + pad)
        canvas[y:y + 128, x:x + 128] = tile
        cv2.putText(canvas, cap, (x + 2, y + 128 + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (220, 220, 220), 1, cv2.LINE_AA)
        cv2.putText(canvas, sub, (x + 2, y + 128 + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (180, 200, 255), 1, cv2.LINE_AA)
    return canvas


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--twin", type=Path, default=DEFAULT_TWIN)
    p.add_argument("--no-crops", action="store_true", help="skip the (slow) crop/montage extraction")
    args = p.parse_args()

    out_dir = args.twin / "label_review"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _rows_with_verdicts(args.twin)
    summary = summarize(rows)
    write_triage(rows, out_dir)
    if not args.no_crops:
        summary["crop_extraction"] = extract_crops(rows, args.twin, out_dir)
    (out_dir / "transition_label_triage_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
