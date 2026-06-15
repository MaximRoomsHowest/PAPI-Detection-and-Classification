"""Held-out TEST-split evaluation of the 2-class serving models (red/white).

Runs ultralytics val for each configured model over the 2-class test view built
by ``build_redwhite_test_view.py`` — once aggregate, once per test flight (the
flights ARE the regimes: 1000 m day wide and 500 m night wide; the day-zoom test
flight is not part of the twin dataset and is reported as absent rather than
invented). Writes one combined JSON artifact for MODELS.md §3.1.2 and
docs/deliverables/06-model-comparison.md to cite.

Run::

    .venv/Scripts/python workflows/scripts/run_redwhite_test_eval.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEW = REPO_ROOT / "data" / "datasets" / "transition-classification-data" / "redwhite_test_view"
OUT = REPO_ROOT / "docs" / "qa-artifacts" / "test-split-eval.json"
CLASS_NAMES = {0: "red", 1: "white"}

MODELS = {
    "yolo26s-fulldata-1280": REPO_ROOT / "models" / "serving" / "best.pt",
    "yolo26n-sequence-1280": REPO_ROOT / "models" / "runs" / "detect" / "yolo26n-sequence-1280" / "weights" / "best.pt",
}

REGIME_BY_FLIGHT = {
    "DJI_202604281946_014_1000": "day_wide_1000m",
    "DJI_202604290007_023_500mrwy06night": "night_wide_500m",
}


def _val(model, data_yaml: Path) -> dict:
    # Full PR curve (val-default conf), IoU 0.5 to match every other published
    # number; workers/batch capped for the 20 MP source frames.
    metrics = model.val(data=str(data_yaml), split="test", imgsz=1280, iou=0.5,
                        batch=4, workers=2, verbose=False,
                        project=str(REPO_ROOT / "data" / "runs" / "detect"),
                        name="redwhite-test", exist_ok=True)
    per_class = {
        name: {"precision": 0.0, "recall": 0.0, "f1": 0.0, "mAP50": 0.0, "support": 0}
        for name in CLASS_NAMES.values()
    }
    support_by_class_id = getattr(metrics, "nt_per_class", None)
    for pos, raw_cls_id in enumerate(getattr(metrics.box, "ap_class_index", [])):
        cls_id = int(raw_cls_id)
        name = CLASS_NAMES.get(cls_id)
        if name is None:
            continue
        p = float(metrics.box.p[pos])
        r = float(metrics.box.r[pos])
        ap50 = float(metrics.box.ap50[pos])
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        support = 0
        if support_by_class_id is not None and cls_id < len(support_by_class_id):
            support = int(support_by_class_id[cls_id])
        per_class[name] = {"precision": round(p, 4), "recall": round(r, 4),
                           "f1": round(f1, 4), "mAP50": round(ap50, 4), "support": support}
    return {
        "per_class": per_class,
        "precision": round(float(metrics.box.mp), 4),
        "recall": round(float(metrics.box.mr), 4),
        "mAP50": round(float(metrics.box.map50), 4),
        "mAP50_95": round(float(metrics.box.map), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", type=Path, default=VIEW)
    args = parser.parse_args()
    from ultralytics import YOLO

    # Stale labels.cache files have silently poisoned re-evals after label
    # changes more than once (MODELS.md §5b documents the rule; this enforces
    # it). Ultralytics keys the cache on the label dir hash, but a rebuilt
    # view with hardlinked images can leave an old cache that still matches —
    # delete outright so every run reads the labels actually on disk.
    for stale_cache in args.view.rglob("labels.cache"):
        stale_cache.unlink()
        print(f"removed stale {stale_cache}")

    result: dict = {
        "dataset": str(args.view),
        "note": (
            "Held-out test split (flight-level, configs/split.yaml) over the 2-class "
            "view of the transition twin: human-corrected red/white boxes; the 6 "
            "test transition boxes are restored to their tracked colours. The "
            "day-zoom test flight is not part of the twin dataset, so no zoom-regime "
            "numbers exist — absent, not zero. Full PR curve (val-default conf), IoU 0.5."
        ),
        "models": {},
    }
    for model_id, weights in MODELS.items():
        if not weights.is_file():
            result["models"][model_id] = {"error": f"weights not found: {weights}"}
            continue
        model = YOLO(str(weights))
        entry = {"weights": str(weights), "aggregate": _val(model, args.view / "data.yaml"), "regimes": {}}
        for flight, regime in REGIME_BY_FLIGHT.items():
            data_yaml = args.view / f"data_{flight}.yaml"
            if data_yaml.is_file():
                entry["regimes"][regime] = _val(model, data_yaml)
        entry["regimes"]["day_zoom"] = {"error": "test flight not present in the twin dataset"}
        result["models"][model_id] = entry

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
