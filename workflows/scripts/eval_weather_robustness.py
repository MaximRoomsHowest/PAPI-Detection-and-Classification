"""Measure detector robustness to synthetic weather, reproducibly, across multiple models.

A scriptable, seeded replacement for the manual notebook-09 flow. For each weather condition it
builds a SEEDED augmented copy of a held-out split (labels copied unchanged — the weather
transforms are non-spatial, so boxes are identical), then runs ``model.val`` for every model and
emits one JSON comparison table with clear-vs-condition deltas.

Works for both detector datasets:

* directory splits (``test: images/test``) — the 2-class flight-split dataset, and
* file-list splits (``test: test.txt``) — the 3-class transition dataset.

Generated datasets land under the gitignored ``data/datasets/weather-eval/`` tree. Stale
``*.cache`` files under those dirs are removed before each val (the documented Ultralytics footgun).

Run::

    .venv/Scripts/python workflows/scripts/eval_weather_robustness.py \
        --data data/datasets/papi-2class-detection-flightsplit/data.yaml --split test \
        --conditions clear rain fog haze snow --severity medium --seed 0 \
        --models nano-weather=models/runs/experiments/yolo26n-weather-flightsplit-1280/weights/best.pt \
                 nano-old=models/runs/detect/yolo26n-sequence-1280/weights/best.pt \
                 small=models/serving/best.pt \
        --out output/weather-robustness-2class.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from weather_aug import apply_weather  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def _img_to_label(p: Path) -> Path:
    """Mirror Ultralytics' img2label: swap the `images` path segment for `labels`, suffix .txt."""
    parts = list(p.parts)
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "images":
            parts[i] = "labels"
            break
    return Path(*parts).with_suffix(".txt")


def _source_images(data_yaml: Path, split: str) -> tuple[list[Path], dict]:
    cfg = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    root = Path(cfg.get("path", data_yaml.parent))
    if not root.is_absolute():
        root = (data_yaml.parent / root).resolve()
    entry = cfg[split]
    target = (root / entry)
    if target.suffix == ".txt" and target.is_file():  # file-list split (transition dataset)
        imgs = []
        for ln in target.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            ip = Path(ln)
            imgs.append(ip if ip.is_absolute() else (root / ip).resolve())
    else:  # directory split (flight-split dataset)
        exts = {".jpg", ".jpeg", ".png", ".bmp"}
        imgs = sorted(p for p in target.rglob("*") if p.suffix.lower() in exts)
    return imgs, cfg.get("names", {})


def _build_condition_dataset(
    images: list[Path], names: dict, condition: str, severity: str, seed: int, dest: Path
) -> Path:
    """Write a weather-augmented copy of the split (images + labels) and a data.yaml; return the yaml."""
    img_dir, lbl_dir = dest / "images", dest / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(images):
        frame = cv2.imread(str(src))  # BGR
        if frame is None:
            continue
        rng = np.random.default_rng(seed + i)  # deterministic per-image draw ("clear" => unchanged)
        aug = apply_weather(frame, condition, severity, rng)
        stem = f"{i:06d}"
        cv2.imwrite(str(img_dir / f"{stem}.jpg"), aug, [cv2.IMWRITE_JPEG_QUALITY, 95])
        src_lbl = _img_to_label(src)
        (lbl_dir / f"{stem}.txt").write_text(
            src_lbl.read_text(encoding="utf-8") if src_lbl.is_file() else "", encoding="utf-8"
        )
    yaml_path = dest / "data.yaml"
    names_block = "".join(f"  {k}: {v}\n" for k, v in sorted(names.items(), key=lambda kv: int(kv[0])))
    yaml_path.write_text(
        f"path: {dest.resolve().as_posix()}\ntrain: images\nval: images\ntest: images\nnames:\n{names_block}",
        encoding="utf-8",
    )
    return yaml_path


def _extract(box, names: dict) -> dict:
    """Aggregate + per-class metrics, mapping per-class arrays via ap_class_index (position-ordered)."""
    per_class: dict[str, dict[str, float]] = {}
    idx = getattr(box, "ap_class_index", None)
    idx = list(idx) if idx is not None else []
    for pos, raw in enumerate(idx):
        cls = int(raw)
        p, r, ap50 = float(box.p[pos]), float(box.r[pos]), float(box.ap50[pos])
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        per_class[str(names.get(cls, names.get(str(cls), cls)))] = {
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "map50": round(ap50, 4),
        }
    return {
        "precision": round(float(box.mp), 4), "recall": round(float(box.mr), 4),
        "map50": round(float(box.map50), 4), "map50_95": round(float(box.map), 4),
        "per_class": per_class,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True, help="Source dataset data.yaml.")
    p.add_argument("--split", default="test", choices=["test", "val", "train"])
    p.add_argument("--conditions", nargs="+", default=["clear", "rain", "fog", "haze", "snow"])
    p.add_argument("--severity", default="medium", choices=["light", "medium", "heavy"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--models", nargs="+", required=True, help="id=path pairs.")
    p.add_argument("--out", type=Path, default=Path("output/weather-robustness.json"))
    p.add_argument("--workdir", type=Path, default=REPO_ROOT / "data" / "datasets" / "weather-eval")
    args = p.parse_args()

    models = {}
    for spec in args.models:
        if "=" not in spec:
            print(f"bad --models spec (need id=path): {spec}", file=sys.stderr)
            return 2
        mid, path = spec.split("=", 1)
        mp = Path(path)
        if not mp.is_file():
            print(f"  [skip] model {mid}: weights not found at {mp}", file=sys.stderr)
            continue
        models[mid] = mp
    if not models:
        print("no usable models", file=sys.stderr)
        return 2

    images, names = _source_images(args.data, args.split)
    print(f"source split '{args.split}': {len(images)} images, classes={names}")

    # Build one augmented dataset per condition (shared across all models).
    ds_root = args.workdir / args.data.parent.name / f"{args.split}-{args.severity}-seed{args.seed}"
    cond_yaml: dict[str, Path] = {}
    for cond in args.conditions:
        dest = ds_root / cond
        cond_yaml[cond] = _build_condition_dataset(images, names, cond, args.severity, args.seed, dest)
        for c in dest.rglob("*.cache"):  # stale-cache footgun
            c.unlink(missing_ok=True)
        print(f"  built {cond}: {cond_yaml[cond]}")

    from ultralytics import YOLO

    results: dict[str, dict[str, dict]] = {c: {} for c in args.conditions}
    for mid, mpath in models.items():
        model = YOLO(str(mpath))
        for cond in args.conditions:
            for c in (ds_root / cond).rglob("*.cache"):
                c.unlink(missing_ok=True)
            m = model.val(data=str(cond_yaml[cond]), split="test", imgsz=args.imgsz, iou=0.5,
                          conf=0.001, batch=args.batch, workers=0, verbose=False, plots=False)
            results[cond][mid] = _extract(m.box, names)
            print(f"  {mid:14s} {cond:8s} mAP50={results[cond][mid]['map50']:.4f} "
                  f"mAP50-95={results[cond][mid]['map50_95']:.4f}")

    # Deltas vs clear (per model).
    deltas: dict[str, dict[str, float]] = {}
    if "clear" in results:
        for mid in models:
            base = results["clear"].get(mid, {}).get("map50")
            if base is None:
                continue
            deltas[mid] = {c: round(results[c][mid]["map50"] - base, 4)
                           for c in args.conditions if mid in results[c]}

    out = {
        "data": str(args.data), "split": args.split, "severity": args.severity, "seed": args.seed,
        "imgsz": args.imgsz, "n_images": len(images), "classes": names,
        "models": {k: str(v) for k, v in models.items()},
        "results": results, "map50_delta_vs_clear": deltas,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
