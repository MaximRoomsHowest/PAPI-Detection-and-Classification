"""Head-to-head: learned (3-class) vs temporal (red<->white flip) transition detection (Phase 8).

Runs the SAME 3-class model over each test flight with ByteTrack, then derives transition events
two ways and scores both against the GT flips (transitions.csv):

* **Track A (learned)** — runs of class-2 (transition) predictions per tracked lamp => one event
  per run. NOTE: single-frame runs COUNT as events (no flicker smoothing); gaps of <=2 frames are
  merged into one run. The published head_to_head.json numbers were produced with exactly this
  behavior (audit WS-5 — an earlier docstring claimed 1-frame flicker smoothing that the code
  never performed; the doc was corrected rather than the method changed, to keep the published
  comparison honest to what ran).
* **Track B (temporal)** — red<->white flips in the model's red/white predictions per tracked
  lamp (class-2 ignored), majority-smoothed over a window => one event per flip. This is the
  existing post-processing method.

Events are matched to GT flips by frame proximity (+/-TOL) at the flight level (robust to the
known lamp-order binding issue). Reports precision / recall / F1 and false-transition rate per
approach. The key question: can the learned class detect real transitions without hallucinating
them during stable red/white?

Run::

    .venv/Scripts/python workflows/scripts/head_to_head_transitions.py \
        --weights models/runs/detect/transition3class-yolo26s-1280/weights/best.pt
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TWIN = REPO_ROOT / "data" / "datasets" / "transition-classification-data"
DEFAULT_WEIGHTS = REPO_ROOT / "models" / "runs" / "detect" / "transition3class-yolo26s-1280" / "weights" / "best.pt"
OUT = REPO_ROOT / "docs" / "transition"
REGIMES = ("daytime", "nighttime")
TOL = 6                 # frame tolerance for matching a detected event to a GT flip
SMOOTH = 3              # majority-smoothing window (frames each side)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _test_videos(twin: Path) -> list[Path]:
    test_imgs = (twin / "transition_combined" / "test.txt").read_text(encoding="utf-8").splitlines()
    vids = []
    for line in test_imgs:
        if line.strip():
            vd = Path(line).parent.parent
            if vd not in vids:
                vids.append(vd)
    return vids


def _smooth_state(seq: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Majority red/white (0/1) per frame over +/-SMOOTH; drops class-2 and noise."""
    rw = [(f, c) for f, c in seq if c in (0, 1)]
    out = []
    for i, (f, _c) in enumerate(rw):
        window = [c for _ff, c in rw[max(0, i - SMOOTH):i + SMOOTH + 1]]
        out.append((f, Counter(window).most_common(1)[0][0]))
    return out


def _track_a_events(seq: list[tuple[int, int]]) -> list[int]:
    """Event frames from runs of class-2 (>=1 frame), merging gaps <=2."""
    t_frames = sorted(f for f, c in seq if c == 2)
    events, run_start, prev = [], None, None
    for f in t_frames:
        if run_start is None:
            run_start = prev = f
        elif f - prev <= 2:
            prev = f
        else:
            events.append((run_start + prev) // 2)
            run_start = prev = f
    if run_start is not None:
        events.append((run_start + prev) // 2)
    return events


def _track_b_events(seq: list[tuple[int, int]]) -> list[int]:
    """Event frames from red<->white flips in the smoothed state."""
    sm = _smooth_state(seq)
    events = []
    for (_fa, sa), (fb, sb) in zip(sm, sm[1:], strict=False):
        if sa != sb:
            events.append(fb)
    return events


def _match(events: list[int], gt: list[int]) -> tuple[int, int, int]:
    """Greedy proximity match -> (tp, fp, fn)."""
    gt_left = sorted(gt)
    used = [False] * len(gt_left)
    tp = 0
    for e in sorted(events):
        best, best_d = -1, TOL + 1
        for i, g in enumerate(gt_left):
            if not used[i] and abs(e - g) <= TOL and abs(e - g) < best_d:
                best, best_d = i, abs(e - g)
        if best >= 0:
            used[best] = True
            tp += 1
    fp = len(events) - tp
    fn = sum(1 for u in used if not u)
    return tp, fp, fn


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f1, 3)}


def run(weights: Path, twin: Path) -> dict:
    from ultralytics import YOLO

    model = YOLO(str(weights))
    agg = {"A": Counter(), "B": Counter()}
    per_flight = {}
    for vd in _test_videos(twin):
        meta = sorted(_read_csv(vd / "metadata.csv"), key=lambda r: int(r["sequence_index"]))
        # Detected events live in the sequence_index domain (see `fr` below). GT flips
        # must be mapped into the SAME domain via to_file -> sequence_index, NOT assumed
        # equal to the raw to_frame_index column (they coincide only by decimation luck).
        seq_by_file = {row["file"]: int(row["sequence_index"]) for row in meta}
        seq_values = set(seq_by_file.values())
        gt: list[int] = []
        if (vd / "transitions.csv").exists():
            for r in _read_csv(vd / "transitions.csv"):
                to_file = (r.get("to_file") or "").strip()
                if to_file:
                    if to_file not in seq_by_file:
                        raise ValueError(f"{vd.name}: transitions.csv to_file {to_file!r} absent from metadata.csv")
                    gt.append(seq_by_file[to_file])
                else:
                    # No to_file column: fall back to the raw index, but fail loudly if it
                    # is not a valid sequence_index — a silent domain mismatch would shift GT.
                    raw = int(r["to_frame_index"])
                    if raw not in seq_values:
                        raise ValueError(
                            f"{vd.name}: transitions.csv has no to_file and to_frame_index {raw} "
                            "is not a sequence_index; cannot align GT to detected events."
                        )
                    gt.append(raw)
        obs: dict[int, list[tuple[int, int]]] = defaultdict(list)
        # persist=False on the first PROCESSED frame, not metadata row 0: if row 0's
        # image is missing, keying the reset on idx==0 would leak the previous
        # flight's ByteTrack state into this one (audit WS-7).
        tracker_started = False
        for row in meta:
            img = vd / "images" / row["file"]
            if not img.exists():
                continue
            res = model.track(str(img), persist=tracker_started, tracker="bytetrack.yaml",
                              imgsz=1280, conf=0.25, verbose=False)[0]
            tracker_started = True
            if res.boxes is None or res.boxes.id is None:
                continue
            fr = int(row["sequence_index"])
            for tid, cls in zip(res.boxes.id.tolist(), res.boxes.cls.tolist(), strict=True):
                obs[int(tid)].append((fr, int(cls)))

        a_events, b_events = [], []
        for seq in obs.values():
            seq.sort()
            a_events += _track_a_events(seq)
            b_events += _track_b_events(seq)
        a = _match(a_events, gt)
        b = _match(b_events, gt)
        per_flight[vd.name] = {"gt_flips": len(gt), "trackA_learned": _prf(*a), "trackB_temporal": _prf(*b)}
        for k, v in zip(("tp", "fp", "fn"), a, strict=True):
            agg["A"][k] += v
        for k, v in zip(("tp", "fp", "fn"), b, strict=True):
            agg["B"][k] += v

    result = {
        "tolerance_frames": TOL,
        "trackA_learned_overall": _prf(agg["A"]["tp"], agg["A"]["fp"], agg["A"]["fn"]),
        "trackB_temporal_overall": _prf(agg["B"]["tp"], agg["B"]["fp"], agg["B"]["fn"]),
        "per_flight": per_flight,
    }
    (OUT / "head_to_head.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    p.add_argument("--twin", type=Path, default=TWIN)
    args = p.parse_args()
    print(json.dumps(run(args.weights, args.twin), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
