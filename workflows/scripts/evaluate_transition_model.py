"""Evaluate the 3-class transition model on the held-out test split (Phase 8).

Reports per-class precision/recall/F1 + confusion (via Ultralytics val on split=test), then mines
example frames into correct_/missed_/false_transition_examples/ and red_white_confusion_examples/
by matching predictions to GT boxes. Overall accuracy is deliberately NOT the headline — the
question is transition recall without hallucinating transitions in stable red/white.

Run::

    .venv/Scripts/python workflows/scripts/evaluate_transition_model.py \
        --weights data/runs/detect/transition3class-yolo11s-1280/weights/best.pt
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WEIGHTS = REPO_ROOT / "data" / "runs" / "detect" / "transition3class-yolo26s-1280" / "weights" / "best.pt"
DEFAULT_DATA = REPO_ROOT / "data" / "datasets" / "transition-classification-data" / "transition_combined" / "data.yaml"
OUT = REPO_ROOT / "docs" / "transition"
EXAMPLES = REPO_ROOT / "data" / "datasets" / "transition-classification-data" / "eval_examples"
CLASS_NAMES = {0: "red", 1: "white", 2: "transition"}


def _iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def _gt_boxes(label_path: Path, w: int, h: int) -> list[tuple[int, tuple]]:
    out = []
    if not label_path.exists():
        return out
    for line in label_path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) != 5:
            continue
        cls = int(p[0])
        cx, cy, bw, bh = (float(v) for v in p[1:])
        out.append((cls, (((cx - bw / 2) * w), ((cy - bh / 2) * h), ((cx + bw / 2) * w), ((cy + bh / 2) * h))))
    return out


def evaluate(weights: Path, data: Path) -> dict:
    from ultralytics import YOLO

    model = YOLO(str(weights))
    # workers/batch capped: source frames are 20MP, so default worker fan-out OOMs the loader.
    metrics = model.val(data=str(data), split="test", imgsz=1280, conf=0.25, iou=0.5,
                        batch=4, workers=2,
                        project=str(REPO_ROOT / "data" / "runs" / "detect"), name="transition3class-test", exist_ok=True)

    per_class = {}
    for i, name in CLASS_NAMES.items():
        try:
            p = float(metrics.box.p[i])
            r = float(metrics.box.r[i])
            ap50 = float(metrics.box.ap50[i])
        except (IndexError, TypeError):
            p = r = ap50 = 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        per_class[name] = {"precision": round(p, 4), "recall": round(r, 4),
                           "f1": round(f1, 4), "mAP50": round(ap50, 4)}
    return {"weights": str(weights), "per_class": per_class,
            "mAP50": round(float(metrics.box.map50), 4), "mAP50_95": round(float(metrics.box.map), 4),
            "val_dir": str(metrics.save_dir)}


def mine_examples(weights: Path, data: Path, per_cat: int = 12) -> dict:
    import cv2
    from ultralytics import YOLO

    if EXAMPLES.exists():
        shutil.rmtree(EXAMPLES)
    cats = ["correct_transition_examples", "missed_transition_examples",
            "false_transition_examples", "red_white_confusion_examples"]
    for c in cats:
        (EXAMPLES / c).mkdir(parents=True, exist_ok=True)

    test_list = (data.parent / "test.txt").read_text(encoding="utf-8").splitlines()
    model = YOLO(str(weights))
    counts = Counter()
    for img_path in test_list:
        if not img_path.strip() or sum(counts[c] for c in cats) >= per_cat * len(cats):
            continue
        ip = Path(img_path)
        label = Path(img_path.replace("/images/", "/labels/")).with_suffix(".txt")
        gt = _gt_boxes(label, 0, 0)
        if not label.exists():
            continue
        img = cv2.imread(str(ip))
        if img is None:
            continue
        h, w = img.shape[:2]
        gt = _gt_boxes(label, w, h)
        res = model.predict(str(ip), imgsz=1280, conf=0.25, iou=0.5, verbose=False)[0]
        preds = [(int(c), tuple(float(v) for v in xyxy)) for c, xyxy in
                 zip(res.boxes.cls.tolist(), res.boxes.xyxy.tolist(), strict=True)]

        gt_t = [b for cls, b in gt if cls == 2]
        pr_t = [b for cls, b in preds if cls == 2]
        cat = None
        # transition correctness
        for gb in gt_t:
            hit = any(_iou(gb, pb) > 0.3 for pb in pr_t)
            cat = "correct_transition_examples" if hit else "missed_transition_examples"
            break
        for pb in pr_t:
            if not any(_iou(gb, pb) > 0.3 for gb in gt_t):
                cat = "false_transition_examples"
        # red/white confusion (GT red matched to pred white or vice versa)
        if cat is None:
            for cls, gb in gt:
                if cls not in (0, 1):
                    continue
                for pc, pb in preds:
                    if pc in (0, 1) and pc != cls and _iou(gb, pb) > 0.4:
                        cat = "red_white_confusion_examples"
        if cat and counts[cat] < per_cat:
            counts[cat] += 1
            annotated = res.plot()
            cv2.imwrite(str(EXAMPLES / cat / f"{ip.parent.parent.name}__{ip.stem}.jpg"), annotated)
    return dict(counts)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--no-examples", action="store_true")
    args = p.parse_args()

    result = evaluate(args.weights, args.data)
    if not args.no_examples:
        result["example_counts"] = mine_examples(args.weights, args.data)

    (OUT / "evaluation_metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
