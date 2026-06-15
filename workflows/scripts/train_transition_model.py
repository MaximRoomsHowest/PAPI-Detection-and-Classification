"""Train the 3-class transition-aware detector (Track A, Phase 7).

INTERIM model: trained on flip-anchored, AI-spot-checked labels (not a full human pass). Two
domain-critical choices:

* **Colour-safe augmentation** — hsv_h=0, hsv_s=0 (hue/saturation jitter would swap
  red<->white<->transition and destroy the label). Only mild brightness (hsv_v) + horizontal
  flip (the detector classifies boxes; lamp ordering is post-processing, so flip is safe).
* **Transition oversampling** — transition is ~3.8% of boxes, so transition-bearing frames are
  duplicated in the train list (val/test keep the true distribution for honest evaluation).

Run::

    .venv/Scripts/python workflows/scripts/train_transition_model.py --epochs 80
    .venv/Scripts/python workflows/scripts/train_transition_model.py --smoke   # 2-epoch config check
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMBINED = REPO_ROOT / "data" / "datasets" / "transition-classification-data" / "transition_combined"
DEFAULT_BASE = REPO_ROOT / "models" / "base" / "yolo26s.pt"
# models/runs/experiments/ is git-ignored: training output stays out of git; promote a finished run to models/runs/detect/ and register it in models/serving/models.json.
DEFAULT_PROJECT = REPO_ROOT / "models" / "runs" / "experiments"
CLASS_NAMES = {0: "papi_light_red", 1: "papi_light_white", 2: "papi_light_transition"}


def _label_for(image_line: str) -> Path:
    return Path(image_line.replace("/images/", "/labels/")).with_suffix(".txt")


def _has_transition(label_path: Path) -> bool:
    return label_path.exists() and any(
        ln.startswith("2 ") for ln in label_path.read_text(encoding="utf-8").splitlines()
    )


def build_oversampled_yaml(combined_dir: Path, factor: int) -> tuple[Path, dict]:
    train_lines = [ln for ln in (combined_dir / "train.txt").read_text(encoding="utf-8").splitlines() if ln.strip()]
    out_lines: list[str] = []
    n_transition_frames = 0
    for img in train_lines:
        reps = factor if _has_transition(_label_for(img)) else 1
        if reps > 1:
            n_transition_frames += 1
        out_lines.extend([img] * reps)
    (combined_dir / "train_oversampled.txt").write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    yaml_path = combined_dir / "data_transition_train.yaml"
    yaml_path.write_text(
        f"path: {combined_dir.resolve().as_posix()}\n"
        "train: train_oversampled.txt\nval: val.txt\ntest: test.txt\nnames:\n"
        + "".join(f"  {i}: {CLASS_NAMES[i]}\n" for i in sorted(CLASS_NAMES)),
        encoding="utf-8",
    )
    return yaml_path, {
        "train_frames_base": len(train_lines),
        "train_frames_oversampled": len(out_lines),
        "transition_frames_oversampled": n_transition_frames,
        "oversample_factor": factor,
    }


def train(args: argparse.Namespace) -> dict:
    import torch
    from ultralytics import YOLO

    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.set_float32_matmul_precision("high")

    if args.resume:
        # Continue an interrupted run from its last.pt (restores optimizer/epoch state); the saved
        # args drive the rest, so the other flags are ignored. Lets a checkpointed run mature
        # without discarding completed epochs.
        run_dir = args.project / args.name
        YOLO(str(run_dir / "weights" / "last.pt")).train(resume=True)
        print(json.dumps({"resumed": str(run_dir)}, indent=2))
        return {"resumed": str(run_dir)}

    yaml_path, oversample = build_oversampled_yaml(args.combined, args.oversample)
    epochs = 2 if args.smoke else args.epochs
    imgsz = 640 if args.smoke else args.imgsz
    name = "smoke-transition3class" if args.smoke else args.name

    model = YOLO(str(args.base))
    model.train(
        data=str(yaml_path), epochs=epochs, imgsz=imgsz, batch=args.batch, device=args.device,
        # colour-safe augmentation. mosaic defaults OFF: source frames are 20MP, so stitching 4
        # per sample exhausts RAM; the colour-safety (hsv_h/s=0) is the constraint that matters.
        hsv_h=0.0, hsv_s=0.0, hsv_v=0.2, fliplr=0.5, flipud=0.0, degrees=0.0,
        translate=0.1, scale=0.5, mosaic=args.mosaic,
        # close_mosaic only matters when mosaic is on; 0 when it's off avoids a no-op/warning.
        close_mosaic=(10 if args.mosaic > 0 else 0), erasing=0.0, mixup=0.0, copy_paste=0.0,
        patience=args.patience, workers=args.workers, seed=0, plots=True, cache=False,
        amp=args.amp,
        project=str(args.project), name=name, exist_ok=True,
    )
    run_dir = args.project / name
    metrics_path = run_dir / "transition_train_meta.json"
    meta = {"base": str(args.base), "data": str(yaml_path), "imgsz": imgsz, "epochs": epochs,
            "batch": args.batch, "workers": args.workers, "amp": args.amp, "oversample": oversample,
            "note": "INTERIM: flip-anchored + AI-spot-checked labels; colour-safe aug; not a full human pass"}
    metrics_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"run_dir": str(run_dir), **oversample}, indent=2))
    return meta


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--combined", type=Path, default=DEFAULT_COMBINED)
    p.add_argument("--base", type=Path, default=DEFAULT_BASE)
    p.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    p.add_argument("--name", default="transition3class-yolo26s-1280")  # base yolo26s (needs ultralytics>=8.4)
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--device", default="0")
    p.add_argument("--patience", type=int, default=15)
    p.add_argument("--workers", type=int, default=0)  # Windows + 20MP frames: avoid spawn-time commit spikes
    p.add_argument("--amp", action="store_true", help="Enable mixed precision after a clean smoke run.")
    p.add_argument(
        "--mosaic",
        type=float,
        default=0.0,
        help="OFF by default. Enabling mosaic reintroduces colour-mixing across lamps "
        "(can corrupt red/white/transition labels) AND high RAM use on 20MP frames.",
    )
    p.add_argument("--oversample", type=int, default=4)
    p.add_argument("--resume", action="store_true", help="continue the run from its last.pt")
    p.add_argument("--smoke", action="store_true")
    args = p.parse_args()
    train(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
