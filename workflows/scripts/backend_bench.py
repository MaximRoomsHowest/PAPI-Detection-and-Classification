"""Fair multi-backend CPU/GPU inference benchmark for the PAPI serving detector.

Complements edge_benchmark.py (single-model, predict-only) by comparing torch (.pt),
ONNX Runtime (.onnx), and OpenVINO (_openvino_model/) for the SAME weights, with every
engine bounded to an identical thread budget via the SHIPPED production code
(app.runtime_threads). It reports p50/p95/p99 AND cores_used (= process CPU-time / wall-time
during the timed loop) so a reader can verify each backend actually stayed within budget —
the fairness flaw that the first §5.4 measurement missed (OpenVINO was unbounded).

Usage (from repo root, via the backend .venv):
  python workflows/scripts/backend_bench.py --threads 2 --device cpu \
      --frames data/eval/builtin-detector-redwhite/images --json-out docs/qa-artifacts/benchmarks/backend-cpu2.json

Note: an in-process thread cap is a PROXY for a cgroup CFS quota; the authoritative cloud
number is this script run inside `docker run --cpus 2 --memory 4g` on the cloud image.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend"))

from app.runtime_threads import (  # noqa: E402
    apply_runtime_threads,
    configure_thread_env,
    install_ort_thread_limit,
    install_ov_thread_limit,
)

# Production detector.py predict args — match real serving so the numbers are representative.
PREDICT = dict(conf=0.4, iou=0.7, imgsz=1280, max_det=4, verbose=False)
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def bench_one(model_path: Path, frames: list, device: str, runs: int, warmup: int) -> dict:
    import psutil
    from ultralytics import YOLO

    args = dict(PREDICT, device=device)
    model = YOLO(str(model_path), task="detect")
    for _ in range(warmup):
        model.predict(frames[0], **args)
    proc = psutil.Process()
    c0 = proc.cpu_times()
    w0 = time.perf_counter()
    lat: list[float] = []
    for _ in range(runs):
        for im in frames:
            t = time.perf_counter()
            model.predict(im, **args)
            lat.append((time.perf_counter() - t) * 1000.0)
    wall = time.perf_counter() - w0
    c1 = proc.cpu_times()
    cpu = (c1.user + c1.system) - (c0.user + c0.system)
    p50 = percentile(lat, 0.50)
    return {
        "model": model_path.name,
        "p50_ms": round(p50, 1),
        "p95_ms": round(percentile(lat, 0.95), 1),
        "p99_ms": round(percentile(lat, 0.99), 1),
        "fps_p50": round(1000.0 / p50, 2) if p50 else None,
        "cores_used": round(cpu / wall, 2) if wall else None,
        "samples": len(lat),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=2, help="thread budget (0=auto)")
    ap.add_argument("--device", default="cpu", help="cpu | cuda")
    ap.add_argument("--frames", type=Path, default=REPO_ROOT / "data/eval/builtin-detector-redwhite/images")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--serving-dir", type=Path, default=REPO_ROOT / "models/serving")
    ap.add_argument("--onnx", type=Path, default=REPO_ROOT / "models/runs/detect/yolo26s-fulldata-1280/weights/best.onnx")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    # Apply the SHIPPED thread-bounding path so the benchmark reflects production.
    n = configure_thread_env(args.threads)
    apply_runtime_threads(n)
    install_ort_thread_limit(n)
    install_ov_thread_limit(n)
    os.environ.setdefault("YOLO_AUTOINSTALL", "False")

    import cv2

    frames = [
        cv2.imread(str(p))
        for p in sorted(args.frames.rglob("*"))
        if p.suffix.lower() in IMAGE_EXTS
    ]
    frames = [f for f in frames if f is not None]
    if not frames:
        raise SystemExit(f"No frames under {args.frames}")

    candidates: list[tuple[str, Path]] = [("torch.pt", args.serving_dir / "best.pt")]
    if args.onnx.is_file():
        candidates.append(("onnx", args.onnx))
    ov_dir = args.serving_dir / "best_openvino_model"
    if ov_dir.is_dir():
        candidates.append(("openvino", ov_dir))

    results = []
    for label, path in candidates:
        if not path.exists():
            continue
        row = bench_one(path, frames, args.device, args.runs, args.warmup)
        row["backend"] = label
        results.append(row)
        print(
            f"{label:<10} p50={row['p50_ms']:>7} p95={row['p95_ms']:>7} p99={row['p99_ms']:>7} "
            f"fps={row['fps_p50']:>6} cores_used={row['cores_used']}"
        )

    report = {
        "device": args.device,
        "threads_resolved": n,
        "host_cores": os.cpu_count(),
        "frames": len(frames),
        "runs": args.runs,
        "warmup": args.warmup,
        "results": results,
    }
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
