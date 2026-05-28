# PAPI Vision — Edge Benchmark

> ⚠ **Template — fill in measurements after running on actual hardware.**
> Placeholders are marked `[TODO]`. This document is intentionally a
> runbook plus an empty results table so the methodology is set
> before numbers are produced (avoids cherry-picking and gives the
> rubric grader a defensible audit trail).

Reproducible methodology for benchmarking PAPI Vision on
resource-constrained hardware. Required for rubric LR1B (real-time
inference, edge deployment, scalability).

## 1. Devices to benchmark

The client requirement is "runs in real-time on a resource-constrained
device". The team should pick at least two of:

| Device | Tier | Why it's interesting |
| --- | --- | --- |
| Raspberry Pi 5 (8 GB) | Embedded | Cheapest credible aviation-edge target |
| NVIDIA Jetson Orin Nano | Embedded + GPU | Real edge GPU; FP16 path |
| Intel NUC (i7-13xxxH) | Industrial PC | Common installed-airport hardware |
| Laptop CPU (i7 / Ryzen 7) | Reference | Establishes the "host" baseline number |

> Pick two minimum. If only laptop is available, benchmark **with**
> and **without** the INT8 ONNX model to surface the cost / value of
> the quantisation step.

## 2. Models to compare

The serving slot holds two artifacts:

```
models/serving/best.pt           # PyTorch float32, ultralytics format
models/serving/best_int8.onnx    # ONNX quantised INT8
```

Plus the base weights:

```
models/base/yolo26n.pt           # Small (n) variant
models/base/yolo26s.pt           # Small-plus (s) variant
models/base/yolov26m.pt          # Medium (m) variant
```

Benchmark **at least** `best.pt` and `best_int8.onnx`. Reporting
both base + fine-tuned is a bonus (shows how training affected
latency, not just accuracy).

## 3. Setup steps

### 3.1 Prepare the device

```bash
# All targets: install Python 3.10+ and project deps
git clone https://github.com/MaximRoomsHowest/PAPI-Detection-and-Classification.git
cd PAPI-Detection-and-Classification
git checkout v1.0
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pip install -r apps/backend/requirements.txt

# For ONNX runtime benchmarking, also:
pip install onnxruntime
# (or onnxruntime-gpu on the Jetson)
```

### 3.2 Prepare a benchmark batch

Pick **100 frames** from the canonical dataset, spread across the
three regimes:

- 40 day / runway 24 / WideCamera
- 40 night / runway 06 / WideCamera
- 20 day / runway 24 / ZoomCamera (cropped)

Stage them in `data/bench/` (or any folder). The exact file names
should be recorded in `data/bench/manifest.csv` so the run is
reproducible.

## 4. Benchmark script

Create `workflows/scripts/edge_benchmark.py` with this skeleton:

```python
#!/usr/bin/env python
"""Edge benchmark — single-frame inference latency + memory footprint."""

import argparse
import csv
import gc
import statistics
import time
from pathlib import Path

import cv2
import psutil
from ultralytics import YOLO


def benchmark(model_path: Path, frames_dir: Path, runs: int = 3, warmup: int = 5) -> dict:
    model = YOLO(str(model_path))

    # Warm-up (first runs are always slow — JIT, allocator, etc.)
    sample = next(frames_dir.glob("*.jpg"))
    img = cv2.imread(str(sample))
    for _ in range(warmup):
        model.predict(img, verbose=False)

    all_latencies = []
    for _ in range(runs):
        for jpg in sorted(frames_dir.glob("*.jpg")):
            img = cv2.imread(str(jpg))
            t0 = time.perf_counter()
            model.predict(img, verbose=False)
            all_latencies.append((time.perf_counter() - t0) * 1000.0)

    process = psutil.Process()
    return {
        "n_frames": len(all_latencies),
        "latency_ms_p50": statistics.median(all_latencies),
        "latency_ms_p95": statistics.quantiles(all_latencies, n=20)[18],
        "latency_ms_p99": statistics.quantiles(all_latencies, n=100)[98],
        "fps_p50": 1000.0 / statistics.median(all_latencies),
        "rss_mb": process.memory_info().rss / (1024 * 1024),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    result = benchmark(args.model, args.frames, args.runs)
    print(result)


if __name__ == "__main__":
    main()
```

Run it once per (device, model) combination:

```bash
python workflows/scripts/edge_benchmark.py \
    --model models/serving/best.pt \
    --frames data/bench/

python workflows/scripts/edge_benchmark.py \
    --model models/serving/best_int8.onnx \
    --frames data/bench/
```

## 5. Results table — [TODO: fill in]

Replace `[TODO]` cells with measured values. **Report median +
P95 + P99**, not just mean — outliers matter for the
"real-time" claim.

### 5.1 Latency (ms / frame)

| Device | Model | p50 | p95 | p99 | fps@p50 |
| --- | --- | ---: | ---: | ---: | ---: |
| Laptop CPU (audit reference) | best.pt | [TODO] | [TODO] | [TODO] | [TODO] |
| Laptop CPU | best_int8.onnx | [TODO] | [TODO] | [TODO] | [TODO] |
| Raspberry Pi 5 | best.pt | [TODO] | [TODO] | [TODO] | [TODO] |
| Raspberry Pi 5 | best_int8.onnx | [TODO] | [TODO] | [TODO] | [TODO] |
| Jetson Orin Nano (FP16) | best.pt | [TODO] | [TODO] | [TODO] | [TODO] |
| Jetson Orin Nano (INT8) | best_int8.onnx | [TODO] | [TODO] | [TODO] | [TODO] |
| Intel NUC i7 | best.pt | [TODO] | [TODO] | [TODO] | [TODO] |

### 5.2 Memory footprint (RSS, MB)

| Device | Model | Baseline (no model) | After load | Steady-state inference |
| --- | --- | ---: | ---: | ---: |
| Laptop CPU | best.pt | [TODO] | [TODO] | [TODO] |
| Raspberry Pi 5 | best.pt | [TODO] | [TODO] | [TODO] |
| Raspberry Pi 5 | best_int8.onnx | [TODO] | [TODO] | [TODO] |
| Jetson Orin Nano | best_int8.onnx | [TODO] | [TODO] | [TODO] |

### 5.3 Accuracy delta (INT8 vs FP32)

Run the *same* verification sample through both models and compute
per-state F1. If quantisation degrades F1 by more than ~3 % the
INT8 path may not be deployable.

| Model | Detection F1 | Per-lamp state F1 |
| --- | ---: | ---: |
| best.pt (FP32 reference) | [TODO] | [TODO] |
| best_int8.onnx | [TODO] | [TODO] |
| Δ | [TODO] | [TODO] |

## 6. Wiring measurements into the frontend

The previous build had a fabricated "edge memory: 412 MB" metric on
the live demo (audit F-CRIT-2). The current build has removed it
because it wasn't real. **Once you fill in §5 above**, you can
reintroduce a real per-device summary card on the Insights page
using the measured numbers — e.g. a small Devices table.

Implementation note: the metric should live in `apps/frontend/src/`
as a static JSON imported at build time, not as part of the API
response (the demo runs in a browser, not on edge hardware).

## 7. Cost projection (rubric LR1D 16+) — [TODO]

After establishing latency + memory numbers, estimate cost-per-airport:

| Component | Unit cost (EUR) | Notes |
| --- | ---: | --- |
| Edge device (Jetson Orin Nano dev kit) | [TODO] | [TODO] |
| DJI Matrice 4E drone | [TODO] | Likely already client-owned |
| Camera mount / housing | [TODO] | [TODO] |
| Connectivity (4G modem + data plan, monthly) | [TODO] | [TODO] |
| Setup labour | [TODO] | Hours × hourly rate |
| **One-time per airport** | **[TODO]** | sum of above |
| **Recurring per airport per month** | **[TODO]** | connectivity + monitoring |

## 8. Conclusion — [TODO]

A short narrative (3-5 sentences) covering:

1. Which device + model combination is recommended for the
   real-time target (≥10 fps).
2. What the cost-per-airport works out to.
3. What the next-step optimisations would be (e.g. TensorRT export,
   model distillation, frame-skip strategy).

Reviewers / jury graders look at this section first.

## 9. Reproducibility

Every cell in the tables above should be recreatable from:

```
git checkout <commit at the time of benchmark>
python workflows/scripts/edge_benchmark.py --model ... --frames data/bench/
```

Commit the manifest of which frames were used (`data/bench/manifest.csv`)
so the same benchmark can be re-run after model changes.
