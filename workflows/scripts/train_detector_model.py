"""Train the 2-class (red/white) Small detector on the leak-free flight-level split.

Companion to ``train_transition_model.py`` (3-class), but for the binary red/white
detector that serves the live demo. Two domain-critical choices, same as the transition
model:

* **Colour-safe augmentation** — ``hsv_h=0, hsv_s=0`` because the class IS the colour:
  any hue/saturation jitter relabels red<->white. Only mild brightness (``hsv_v``) and a
  horizontal flip (the detector classifies boxes; lamp ordering is post-processing) are
  applied. ``mosaic/mixup/copy_paste/erasing=0`` (4-frame stitching mixes lamp colours and
  exhausts RAM on 20MP frames).
* **Flight-level split** — the dataset assigns whole flights to train/val/test, so
  no near-duplicate frames leak across the split (unlike the random-split serving model).

No transition oversampling here (red/white are ~55/45, already balanced).

After training, runs an honest held-out **test**-split evaluation at the full PR curve
(conf=0.001), mapping per-class metrics via ``ap_class_index`` (Ultralytics orders the
per-class arrays by position among classes present, not by class id).

Run::

    .venv/Scripts/python workflows/scripts/train_detector_model.py            # full 80-epoch run
    .venv/Scripts/python workflows/scripts/train_detector_model.py --smoke    # 2-epoch config check
    .venv/Scripts/python workflows/scripts/train_detector_model.py --resume   # continue from last.pt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = REPO_ROOT / "data" / "datasets" / "papi-2class-detection-flightsplit" / "data.yaml"
DEFAULT_BASE = REPO_ROOT / "models" / "base" / "yolo26s.pt"
DEFAULT_PROJECT = REPO_ROOT / "models" / "runs" / "experiments"
CLASS_NAMES = {0: "papi_light_red", 1: "papi_light_white"}


def _test_metrics(model, data: Path, imgsz: int, project: Path, name: str) -> dict:
    """Honest held-out test-split eval at the full PR curve (conf=0.001), per-class via ap_class_index."""
    metrics = model.val(
        data=str(data), split="test", imgsz=imgsz, iou=0.5, conf=0.001, batch=4, workers=0,
        project=str(project), name=f"{name}-test", exist_ok=True, verbose=False, plots=False,
    )
    box = metrics.box
    per_class: dict[str, dict[str, float]] = {}
    idx = getattr(box, "ap_class_index", None)
    idx = list(idx) if idx is not None else []
    for pos, raw in enumerate(idx):
        cls = int(raw)
        p, r, ap50 = float(box.p[pos]), float(box.r[pos]), float(box.ap50[pos])
        f1 = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0
        per_class[CLASS_NAMES.get(cls, str(cls))] = {
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "map50": round(ap50, 4),
        }
    return {
        "precision": round(float(box.mp), 4), "recall": round(float(box.mr), 4),
        "map50": round(float(box.map50), 4), "map50_95": round(float(box.map), 4),
        "per_class": per_class,
        "note": "Held-out TEST split (flight-level), full PR curve (conf=0.001, iou=0.5).",
    }


def _cap_cpu_threads(n: int) -> None:
    """Bound the data-pipeline's CPU thread fan-out so it can't oversubscribe the host.

    The dataloader workers' OpenCV/NumPy/BLAS pools each default to *all* logical cores,
    so `workers` × all-cores → thread thrash that pegs the CPU and freezes the machine
    (observed at 96% on a 24-core box). The *_NUM_THREADS env vars are inherited by every
    spawned worker, so they cap decode/augment per worker; torch/cv2 calls cap the main
    process. Set BEFORE importing torch/cv2 (libraries read these at import)."""
    import os

    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[var] = str(n)


def train(args: argparse.Namespace) -> dict:
    _cap_cpu_threads(args.cpu_threads)
    import torch
    from ultralytics import YOLO

    torch.set_num_threads(args.cpu_threads)
    try:
        import cv2

        cv2.setNumThreads(args.cpu_threads)
    except Exception:  # noqa: BLE001 - thread-cap is best-effort; never block training on it
        pass

    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")

    if args.resume:
        run_dir = args.project / args.name
        YOLO(str(run_dir / "weights" / "last.pt")).train(resume=True)
        print(json.dumps({"resumed": str(run_dir)}, indent=2))
        return {"resumed": str(run_dir)}

    epochs = 2 if args.smoke else args.epochs
    imgsz = 640 if args.smoke else args.imgsz
    name = "smoke-detector2class" if args.smoke else args.name

    model = YOLO(str(args.base))
    model.train(
        data=str(args.data), epochs=epochs, imgsz=imgsz, batch=args.batch, device=args.device,
        # Colour-safe augmentation: hue/sat jitter would swap red<->white (class == colour).
        hsv_h=0.0, hsv_s=0.0, hsv_v=0.2, fliplr=0.5, flipud=0.0, degrees=0.0,
        translate=0.1, scale=0.5, shear=0.0, perspective=0.0,
        mosaic=0.0, close_mosaic=0, mixup=0.0, copy_paste=0.0, erasing=0.0, auto_augment=None,
        patience=args.patience, workers=args.workers, seed=0, plots=True, cache=False, amp=args.amp,
        project=str(args.project), name=name, exist_ok=True,
    )
    run_dir = args.project / name
    best = run_dir / "weights" / "best.pt"

    test = None
    if not args.smoke and best.is_file():
        try:
            test = _test_metrics(YOLO(str(best)), args.data, imgsz, args.project, name)
        except Exception as exc:  # noqa: BLE001 - training already saved; test eval is best-effort
            test = {"error": str(exc)}

    meta = {
        "base": str(args.base), "data": str(args.data), "imgsz": imgsz, "epochs": epochs,
        "batch": args.batch, "workers": args.workers, "amp": args.amp,
        "augmentation": "colour-safe (hsv_h/s=0, hsv_v=0.2, fliplr=0.5, no mosaic/mixup/copy_paste/erasing)",
        "split": "flight-level (leak-free) from configs/split.yaml",
        "classes": CLASS_NAMES, "best_weights": str(best), "test_metrics": test,
    }
    (run_dir / "detector_train_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), "best": str(best), "test_metrics": test}, indent=2))
    return meta


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=DEFAULT_DATA)
    p.add_argument("--base", type=Path, default=DEFAULT_BASE)
    p.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    p.add_argument("--name", default="yolo26s-2class-flightsplit-1280")
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--device", default="0")
    p.add_argument("--patience", type=int, default=15)
    # The dataset builder pre-downscales frames to ~1.5MP, so parallel data loading no
    # longer risks the Windows 20MP spawn-commit spikes that forced workers=0 elsewhere.
    p.add_argument("--workers", type=int, default=4)
    # Per-process CPU thread cap for the data pipeline (OpenCV/NumPy/BLAS + torch). Keeps
    # `workers` x threads well under the host core count so training can't peg the CPU and
    # freeze the machine. workers=4 x cpu_threads=4 = 16 threads, leaving headroom on a
    # 24-core box for Docker + the OS. Lower it further on a busy machine.
    p.add_argument("--cpu-threads", type=int, default=4, dest="cpu_threads")
    # Mixed precision: ~1.5-2x faster + lower VRAM on the 4070, negligible accuracy cost
    # for detection. On by default now that the pipeline is smoke-validated; --no-amp opts out.
    p.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True,
                   help="Mixed-precision training (default on; --no-amp to disable).")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--resume", action="store_true")
    args = p.parse_args()
    train(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
