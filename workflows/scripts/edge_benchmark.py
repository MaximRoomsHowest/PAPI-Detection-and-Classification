#!/usr/bin/env python
"""Benchmark PAPI model inference latency on local or edge hardware.

The script intentionally measures model prediction only, not upload,
database writes, or frontend rendering. It emits JSON by default and can
also write a CSV row for the edge-benchmark report.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
    except Exception:
        return None


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
    return round(ordered[index], 3)


def load_frames(frames_dir: Path, limit: int | None) -> list[Any]:
    import cv2

    paths = [
        path
        for path in sorted(frames_dir.rglob("*"))
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if limit:
        paths = paths[:limit]
    if not paths:
        raise ValueError(f"No benchmark images found under {frames_dir}")

    frames = []
    for path in paths:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Could not read benchmark image: {path}")
        frames.append((path, image))
    return frames


def benchmark(
    model_path: Path,
    frames_dir: Path,
    device_label: str,
    inference_device: str,
    runs: int,
    warmup: int,
    limit: int | None,
) -> dict[str, Any]:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    base = {
        "started_at": started_at,
        "git_sha": git_sha(),
        "device_label": device_label,
        "machine": platform.platform(),
        "python": platform.python_version(),
        "model_path": str(model_path),
        "model_name": model_path.name,
        "model_format": model_path.suffix.lower().lstrip(".") or "unknown",
        "frames_dir": str(frames_dir),
        "inference_device": inference_device,
        "runs": runs,
        "warmup": warmup,
        "error": None,
    }

    try:
        os.environ.setdefault("YOLO_AUTOINSTALL", "False")
        from ultralytics import YOLO

        frames = load_frames(frames_dir, limit)
        baseline_rss = rss_mb()
        load_start = time.perf_counter()
        model = YOLO(str(model_path))
        load_ms = (time.perf_counter() - load_start) * 1000
        after_load_rss = rss_mb()

        sample = frames[0][1]
        for _ in range(warmup):
            model.predict(sample, device=inference_device, verbose=False)

        latencies = []
        for _ in range(runs):
            for _, image in frames:
                t0 = time.perf_counter()
                model.predict(image, device=inference_device, verbose=False)
                latencies.append((time.perf_counter() - t0) * 1000)

        p50 = percentile(latencies, 0.50)
        result = {
            **base,
            "frame_count": len(frames),
            "prediction_count": len(latencies),
            "load_ms": round(load_ms, 3),
            "latency_ms_p50": p50,
            "latency_ms_p95": percentile(latencies, 0.95),
            "latency_ms_p99": percentile(latencies, 0.99),
            "fps_p50": round(1000.0 / p50, 3) if p50 else None,
            "rss_mb_baseline": baseline_rss,
            "rss_mb_after_load": after_load_rss,
            "rss_mb_after_inference": rss_mb(),
        }
        return result
    except Exception as exc:
        return {
            **base,
            "frame_count": 0,
            "prediction_count": 0,
            "load_ms": None,
            "latency_ms_p50": None,
            "latency_ms_p95": None,
            "latency_ms_p99": None,
            "fps_p50": None,
            "rss_mb_baseline": rss_mb(),
            "rss_mb_after_load": None,
            "rss_mb_after_inference": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def write_json(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def append_csv(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(result.keys())
    rows: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            existing_fields = reader.fieldnames or []
            rows = list(reader)
        for field in existing_fields:
            if field not in fields:
                fields.append(field)
        if existing_fields != fields:
            rows.append(result)
            with path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            return

    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--device-label", default=platform.node() or "local")
    parser.add_argument("--inference-device", default="cpu")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--csv-out", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = benchmark(
        model_path=args.model,
        frames_dir=args.frames,
        device_label=args.device_label,
        inference_device=args.inference_device,
        runs=args.runs,
        warmup=args.warmup,
        limit=args.limit,
    )
    print(json.dumps(result, indent=2))
    if args.json_out:
        write_json(args.json_out, result)
    if args.csv_out:
        append_csv(args.csv_out, result)
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
