"""Before/after: false-transition rate of two transition models on the clean test split.

The headline question for the audit is the user's complaint -- "stable white/red lamps classified as
transition" -- which is measurable across the ~1.4k stable boxes regardless of the tiny transition GT
count. For each model this counts every class-2 PREDICTION and buckets it by the GT box it overlaps:
  * true_transition   -- overlaps a real transition GT (good)
  * FALSE_on_stable   -- overlaps a red/white GT  (THE bug: stable lamp called transition)
  * spurious          -- overlaps nothing
plus transition-GT recall. Run::

    .venv/Scripts/python workflows/scripts/compare_transition_false_rate.py \
        --old models/runs/detect/transition3class-yolo26s-1280/weights/best.pt \
        --new models/runs/detect/transition3class-yolo26s-1280-clean/weights/best.pt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO_ROOT / "data" / "datasets" / "transition-classification-data" / "transition_combined"


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1, ix2, iy2 = max(ax1, bx1), max(ay1, by1), min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _gt(label_path: Path, w: int, h: int):
    out = []
    if not label_path.exists():
        return out
    for line in label_path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) != 5:
            continue
        cls = int(p[0])
        cx, cy, bw, bh = (float(v) for v in p[1:])
        out.append((cls, ((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h)))
    return out


def assess(weights: Path, images: list[str], conf: float) -> dict:
    import cv2
    from ultralytics import YOLO

    model = YOLO(str(weights))
    true_t = false_stable = spurious = 0
    gt_total = gt_hit = 0
    for img in images:
        ip = Path(img)
        lp = Path(img.replace("/images/", "/labels/")).with_suffix(".txt")
        im = cv2.imread(str(ip))
        if im is None:
            continue
        h, w = im.shape[:2]
        gt = _gt(lp, w, h)
        gt_t = [b for c, b in gt if c == 2]
        gt_total += len(gt_t)
        res = model.predict(str(ip), imgsz=1280, conf=conf, iou=0.5, verbose=False)[0]
        preds = [(int(c), tuple(float(v) for v in xy))
                 for c, xy in zip(res.boxes.cls.tolist(), res.boxes.xyxy.tolist(), strict=True)]
        pr_t = [b for c, b in preds if c == 2]
        for pb in pr_t:
            best_c, best_iou = None, 0.0
            for gc, gb in gt:
                i = _iou(pb, gb)
                if i > best_iou:
                    best_c, best_iou = gc, i
            if best_iou < 0.3:
                spurious += 1
            elif best_c == 2:
                true_t += 1
            else:
                false_stable += 1
        for gb in gt_t:
            if any(_iou(gb, pb) > 0.3 for pb in pr_t):
                gt_hit += 1
    pred_t = true_t + false_stable + spurious
    return {
        "weights": weights.name, "conf": conf,
        "transition_predictions": pred_t,
        "true_transition": true_t,
        "FALSE_on_stable_redwhite": false_stable,
        "spurious_no_gt": spurious,
        "false_transition_rate": round(false_stable / pred_t, 3) if pred_t else None,
        "transition_gt": gt_total, "transition_gt_detected": gt_hit,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old", type=Path, required=True)
    ap.add_argument("--new", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()
    images = [ln for ln in (args.data / "test.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    result = {"test_images": len(images),
              "old": assess(args.old, images, args.conf),
              "new": assess(args.new, images, args.conf)}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
